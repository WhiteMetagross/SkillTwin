import base64
import json
from typing import Any, Dict, List, Optional
from .imageCaptioner import ImageCaption
from .observer import ALLOWED_CANDIDATE_ACTIONS, LocalMediaObserver, MediaObserver, Observation
from .transcriber import TranscriptSegment
from .videoSampler import SampledFrame

class BedrockObserver(MediaObserver):
    """
    Multimodal media observer using Amazon Bedrock foundation models.
    Analyzes sampled video frames, transcript segments, and reference image context.
    Safely handles malformed responses and falls back to deterministic local observer.
    """

    def __init__(
        self,
        bedrockClient: Optional[Any] = None,
        modelId: str = "anthropic.claude-3-5-sonnet-20240620-v1:0",
        fallbackObserver: Optional[MediaObserver] = None
    ) -> None:
        self.bedrockClient = bedrockClient
        self.modelId = modelId
        self.fallbackObserver = fallbackObserver or LocalMediaObserver()

    def _getClient(self) -> Any:
        if self.bedrockClient is not None:
            return self.bedrockClient
        import boto3
        return boto3.client("bedrock-runtime")

    def observeVideo(
        self,
        videoId: str,
        skillId: str,
        frames: List[SampledFrame],
        transcriptSegments: List[TranscriptSegment],
        referenceCaptions: Optional[List[ImageCaption]] = None
    ) -> List[Observation]:
        if not frames:
            return []

        try:
            client = self._getClient()

            # Limit to 4 key frames to stay within model token constraints
            step = max(1, len(frames) // 4)
            selectedFrames = frames[::step][:4]

            contentPayload: List[Dict[str, Any]] = []
            for frame in selectedFrames:
                encoded = base64.b64encode(frame.imageBytes).decode("utf-8")
                contentPayload.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": encoded
                    }
                })

            transcriptsSummary = "\n".join([f"{s.startMs}ms - {s.endMs}ms: {s.text}" for s in transcriptSegments])
            prompt = (
                f"You are a SkillTwin media observer analyzing video '{videoId}'. "
                f"Transcript segments:\n{transcriptsSummary}\n\n"
                f"Return a JSON array of observations. Each object must have: "
                f"startMs (int), endMs (int), beforeState (str), action (str), afterState (str), "
                f"visibleObjects (list of str), spokenEvidence (str or null), "
                f"candidateAction (must be one of: {sorted(list(ALLOWED_CANDIDATE_ACTIONS))}), "
                f"referenceFrameKey (str matching one of the frames), confidence (float between 0.0 and 1.0)."
            )

            contentPayload.append({
                "type": "text",
                "text": prompt
            })

            bodyPayload = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1024,
                "temperature": 0.0,
                "messages": [
                    {
                        "role": "user",
                        "content": contentPayload
                    }
                ]
            }

            response = client.invoke_model(
                modelId=self.modelId,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(bodyPayload)
            )

            rawBody = response["body"].read()
            parsed = json.loads(rawBody)

            contentBlocks = parsed.get("content", [])
            textOutput = ""
            for block in contentBlocks:
                if block.get("type") == "text":
                    textOutput += block.get("text", "")

            structuredObservations = json.loads(textOutput)
            if not isinstance(structuredObservations, list):
                raise ValueError("Expected JSON array of observations from Bedrock")

            validObservations: List[Observation] = []
            for item in structuredObservations:
                candidate = item.get("candidateAction", "")
                if candidate not in ALLOWED_CANDIDATE_ACTIONS:
                    raise ValueError(f"Invalid candidateAction from model: {candidate}")

                conf = float(item.get("confidence", 0.9))
                if conf < 0.0 or conf > 1.0:
                    raise ValueError(f"Confidence out of range: {conf}")

                startMs = int(item.get("startMs", 0))
                endMs = int(item.get("endMs", startMs + 1000))
                if endMs <= startMs:
                    endMs = startMs + 1000

                refKey = item.get("referenceFrameKey") or selectedFrames[0].storageKey

                validObservations.append(
                    Observation(
                        observationId="obs-pending",
                        videoId=videoId,
                        startMs=startMs,
                        endMs=endMs,
                        beforeState=item.get("beforeState", "initial state"),
                        action=item.get("action", "executed action"),
                        afterState=item.get("afterState", "resulting state"),
                        visibleObjects=item.get("visibleObjects", ["item"]),
                        spokenEvidence=item.get("spokenEvidence"),
                        candidateAction=candidate,
                        referenceFrameKey=refKey,
                        confidence=conf
                    )
                )

            return validObservations if validObservations else self.fallbackObserver.observeVideo(
                videoId, skillId, frames, transcriptSegments, referenceCaptions
            )
        except Exception:
            return self.fallbackObserver.observeVideo(
                videoId, skillId, frames, transcriptSegments, referenceCaptions
            )
