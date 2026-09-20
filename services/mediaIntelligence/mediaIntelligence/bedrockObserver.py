import base64
import json
from typing import Any, Dict, List, Optional, Sequence

from .imageCaptioner import ImageCaption
from .observer import ALLOWED_CANDIDATE_ACTIONS, MediaObserver, Observation
from .transcriber import TranscriptSegment
from .videoSampler import SampledFrame


class BedrockObserver(MediaObserver):
    """Windowed, fail-closed Amazon Bedrock multimodal observer."""

    def __init__(
        self,
        bedrockClient: Optional[Any] = None,
        modelId: str = "anthropic.claude-3-5-sonnet-20240620-v1:0",
        windowDurationMs: int = 12000,
        maxFramesPerWindow: int = 4
    ) -> None:
        self.bedrockClient = bedrockClient
        self.modelId = modelId
        self.windowDurationMs = max(1000, windowDurationMs)
        self.maxFramesPerWindow = max(1, min(maxFramesPerWindow, 8))

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
        referenceCaptions: Optional[List[ImageCaption]] = None,
        videoDurationMs: Optional[int] = None
    ) -> List[Observation]:
        del skillId
        if not frames:
            return []
        orderedFrames = sorted(frames, key=lambda frame: frame.timestampMs)
        totalDurationMs = videoDurationMs or max(orderedFrames[-1].timestampMs + 1000, 1000)
        if totalDurationMs <= 0:
            return []

        observations: List[Observation] = []
        try:
            client = self._getClient()
            for windowStart in range(0, totalDurationMs, self.windowDurationMs):
                windowEnd = min(windowStart + self.windowDurationMs, totalDurationMs)
                windowFrames = [
                    frame for frame in orderedFrames
                    if windowStart <= frame.timestampMs < windowEnd
                ]
                if not windowFrames:
                    raise ValueError(
                        f"No sampled frame covers window {windowStart}ms-{windowEnd}ms"
                    )
                selectedFrames = self._selectFrames(windowFrames)
                windowSegments = [
                    segment for segment in transcriptSegments
                    if max(windowStart, segment.startMs) < min(windowEnd, segment.endMs)
                ]
                response = client.invoke_model(
                    modelId=self.modelId,
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps(self._buildRequest(
                        videoId,
                        windowStart,
                        windowEnd,
                        selectedFrames,
                        windowSegments,
                        referenceCaptions or []
                    ))
                )
                observations.extend(self._parseResponse(
                    response,
                    videoId,
                    windowStart,
                    windowEnd,
                    selectedFrames,
                    windowSegments,
                    totalDurationMs
                ))
        except Exception:
            return []

        observations.sort(key=lambda item: (item.startMs, item.endMs))
        return self._deduplicate(observations)

    def _selectFrames(self, frames: Sequence[SampledFrame]) -> List[SampledFrame]:
        if len(frames) <= self.maxFramesPerWindow:
            return list(frames)
        if self.maxFramesPerWindow == 1:
            return [frames[len(frames) // 2]]
        lastIndex = len(frames) - 1
        indexes = {
            round(position * lastIndex / (self.maxFramesPerWindow - 1))
            for position in range(self.maxFramesPerWindow)
        }
        return [frames[index] for index in sorted(indexes)]

    def _buildRequest(
        self,
        videoId: str,
        windowStart: int,
        windowEnd: int,
        frames: Sequence[SampledFrame],
        transcriptSegments: Sequence[TranscriptSegment],
        referenceCaptions: Sequence[ImageCaption]
    ) -> Dict[str, Any]:
        content: List[Dict[str, Any]] = []
        for frame in frames:
            content.append({
                "type": "text",
                "text": (
                    f"SUPPLIED_VIDEO_FRAME timestampMs={frame.timestampMs} "
                    f"storageKey={frame.storageKey}"
                )
            })
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.b64encode(frame.imageBytes).decode("utf-8")
                }
            })

        transcriptText = "\n".join(
            f"{segment.startMs}-{segment.endMs}ms: {segment.text}"
            for segment in transcriptSegments
        ) or "NONE"
        contextText = "\n".join(
            f"{caption.imageId}: {caption.caption}"
            for caption in referenceCaptions
        ) or "NONE"
        allowedActions = ", ".join(sorted(ALLOWED_CANDIDATE_ACTIONS))
        content.append({
            "type": "text",
            "text": (
                f"Analyze video {videoId}, window {windowStart}-{windowEnd}ms.\n"
                f"WINDOW_TRANSCRIPT (acoustic evidence only):\n{transcriptText}\n"
                f"REFERENCE_IMAGE_CONTEXT (context only, never claim it was observed in video):\n"
                f"{contextText}\n"
                "Return a JSON array only. Every observation must be supported by visible pixels "
                "in a SUPPLIED_VIDEO_FRAME. Do not invent missing template actions. Required fields: "
                "startMs, endMs, beforeState, action, afterState, visibleObjects, spokenEvidence, "
                "candidateAction, referenceFrameKey, confidence. referenceFrameKey must exactly match "
                "a supplied storageKey. spokenEvidence must be null or an exact transcript excerpt. "
                f"candidateAction must be one of: {allowedActions}."
            )
        })
        return {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1400,
            "temperature": 0.0,
            "messages": [{"role": "user", "content": content}]
        }

    def _parseResponse(
        self,
        response: Dict[str, Any],
        videoId: str,
        windowStart: int,
        windowEnd: int,
        frames: Sequence[SampledFrame],
        transcriptSegments: Sequence[TranscriptSegment],
        totalDurationMs: int
    ) -> List[Observation]:
        rawBody = response["body"].read()
        providerPayload = json.loads(rawBody)
        textOutput = "".join(
            block["text"]
            for block in providerPayload.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text" and "text" in block
        )
        items = json.loads(textOutput)
        if not isinstance(items, list):
            raise ValueError("Bedrock response must contain a JSON array")

        suppliedKeys = {frame.storageKey for frame in frames}
        transcriptText = " ".join(segment.text for segment in transcriptSegments).casefold()
        parsed: List[Observation] = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Observation must be an object")
            required = {
                "startMs", "endMs", "beforeState", "action", "afterState",
                "visibleObjects", "spokenEvidence", "candidateAction",
                "referenceFrameKey", "confidence"
            }
            if set(item) != required:
                raise ValueError("Observation fields are missing or unexpected")

            startMs = self._strictInteger(item["startMs"], "startMs")
            endMs = self._strictInteger(item["endMs"], "endMs")
            if startMs < windowStart or endMs > windowEnd or endMs > totalDurationMs:
                raise ValueError("Observation interval is outside the supplied video window")
            if endMs <= startMs:
                raise ValueError("Observation interval is not positive")

            beforeState = self._nonemptyString(item["beforeState"], "beforeState")
            action = self._nonemptyString(item["action"], "action")
            afterState = self._nonemptyString(item["afterState"], "afterState")
            visibleObjects = item["visibleObjects"]
            if (
                not isinstance(visibleObjects, list)
                or not visibleObjects
                or any(not isinstance(value, str) or not value.strip() for value in visibleObjects)
            ):
                raise ValueError("visibleObjects must contain nonempty visible facts")

            candidateAction = item["candidateAction"]
            if candidateAction not in ALLOWED_CANDIDATE_ACTIONS:
                raise ValueError("candidateAction is unsupported")
            referenceFrameKey = item["referenceFrameKey"]
            if referenceFrameKey not in suppliedKeys:
                raise ValueError("referenceFrameKey was not supplied to this model window")

            confidence = item["confidence"]
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
                raise ValueError("confidence must be numeric")
            confidence = float(confidence)
            if not 0.0 <= confidence <= 1.0:
                raise ValueError("confidence is outside 0.0 to 1.0")

            spokenEvidence = item["spokenEvidence"]
            if spokenEvidence is not None:
                spokenEvidence = self._nonemptyString(spokenEvidence, "spokenEvidence")
                if not transcriptText or spokenEvidence.casefold() not in transcriptText:
                    raise ValueError("spokenEvidence is not an exact supplied transcript excerpt")

            parsed.append(Observation(
                observationId="obs-pending",
                videoId=videoId,
                startMs=startMs,
                endMs=endMs,
                beforeState=beforeState,
                action=action,
                afterState=afterState,
                visibleObjects=[value.strip() for value in visibleObjects],
                spokenEvidence=spokenEvidence,
                candidateAction=candidateAction,
                referenceFrameKey=referenceFrameKey,
                confidence=confidence
            ))
        return parsed

    def _deduplicate(self, observations: Sequence[Observation]) -> List[Observation]:
        deduplicated: List[Observation] = []
        for observation in observations:
            duplicate = next((
                current for current in reversed(deduplicated)
                if current.candidateAction == observation.candidateAction
                and current.action.casefold() == observation.action.casefold()
                and observation.startMs <= current.endMs
            ), None)
            if duplicate is None:
                deduplicated.append(observation)
                continue
            duplicate.endMs = max(duplicate.endMs, observation.endMs)
            if observation.confidence > duplicate.confidence:
                duplicate.referenceFrameKey = observation.referenceFrameKey
                duplicate.confidence = observation.confidence
            duplicate.visibleObjects = list(dict.fromkeys(
                duplicate.visibleObjects + observation.visibleObjects
            ))
            if observation.spokenEvidence and observation.spokenEvidence != duplicate.spokenEvidence:
                duplicate.spokenEvidence = " ".join(filter(None, [
                    duplicate.spokenEvidence,
                    observation.spokenEvidence
                ]))
        return deduplicated

    @staticmethod
    def _strictInteger(value: Any, fieldName: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{fieldName} must be an integer")
        return value

    @staticmethod
    def _nonemptyString(value: Any, fieldName: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{fieldName} must be a nonempty string")
        return value.strip()
