import base64
import json
from typing import Any, Dict, Optional
from .visionEvaluator import VisionEvaluationResult, VisionEvaluator

class BedrockVisionEvaluator(VisionEvaluator):
    """
    Multimodal vision evaluator using Amazon Bedrock to verify worker execution photos.
    Validates structured model responses and fails closed on provider, network, or parsing errors.
    Never falls back to an evaluator that could produce an unearned pass verdict.
    """

    def __init__(
        self,
        bedrockClient: Optional[Any] = None,
        modelId: str = "anthropic.claude-3-5-sonnet-20240620-v1:0"
    ) -> None:
        self.bedrockClient = bedrockClient
        self.modelId = modelId

    def _getClient(self) -> Any:
        if self.bedrockClient is not None:
            return self.bedrockClient
        import boto3
        return boto3.client("bedrock-runtime")

    def evaluateImage(
        self,
        imageBytes: bytes,
        stepCriteria: Dict[str, Any],
        referenceImageBytes: Optional[bytes] = None
    ) -> VisionEvaluationResult:
        if not imageBytes or len(imageBytes) < 32:
            return VisionEvaluationResult(
                verdict="uncertain",
                confidence=0.0,
                observed=[],
                missing=[],
                message="Missing or unreadable image file, please capture another photo",
                correction="Ensure camera lens is clean and retry capture"
            )

        try:
            client = self._getClient()
            encodedImage = base64.b64encode(imageBytes).decode("utf-8")

            prompt = (
                f"You are a SkillTwin packing quality verifier. "
                f"Evaluate the worker photo against step '{stepCriteria.get('actionCode')}': "
                f"{stepCriteria.get('instruction')}. Return JSON with verdict ('pass', 'fail', 'uncertain'), "
                f"confidence (0.0 to 1.0), observed (list of strings), missing (list of strings), "
                f"message (string), and correction (string or null)."
            )

            payload = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 512,
                "temperature": 0.0,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": encodedImage
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            }

            response = client.invoke_model(
                modelId=self.modelId,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(payload)
            )

            rawBody = response["body"].read()
            parsedBody = json.loads(rawBody)

            contentBlocks = parsedBody.get("content", [])
            textOutput = ""
            for block in contentBlocks:
                if block.get("type") == "text":
                    textOutput += block.get("text", "")

            structured = json.loads(textOutput)
            return self._validateResult(structured)
        except Exception:
            # Bedrock vision provider failure must fail closed by returning uncertain
            return VisionEvaluationResult(
                verdict="uncertain",
                confidence=0.0,
                observed=[],
                missing=[],
                message="Bedrock vision verification service unavailable, please retake photo",
                correction="Hold camera steady and retake photo"
            )

    def _validateResult(self, data: Dict[str, Any]) -> VisionEvaluationResult:
        verdict = data.get("verdict")
        confidence = data.get("confidence")
        observed = data.get("observed")
        missing = data.get("missing")
        message = data.get("message")
        correction = data.get("correction")

        if verdict not in ("pass", "fail", "uncertain"):
            raise ValueError(f"Invalid verdict from model: {verdict}")
        if not isinstance(confidence, (int, float)) or confidence < 0.0 or confidence > 1.0:
            raise ValueError(f"Invalid confidence from model: {confidence}")
        if not isinstance(observed, list):
            raise ValueError("Malformed observed field from model")
        if not isinstance(missing, list):
            raise ValueError("Malformed missing field from model")
        if not isinstance(message, str):
            raise ValueError("Malformed message field from model")

        return VisionEvaluationResult(
            verdict=verdict,
            confidence=float(confidence),
            observed=observed,
            missing=missing,
            message=message,
            correction=correction
        )
