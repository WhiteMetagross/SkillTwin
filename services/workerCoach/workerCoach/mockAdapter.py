from typing import Any, Dict, Literal, Optional
from .contentResolver import ContentResolver, LocalContentResolver
from .validator import validateSchema
from .visionEvaluator import (
    LocalCriteriaVisionEvaluator,
    MockCriteriaVisionEvaluator,
    VisionEvaluator,
)

MockVerdict = Literal["pass", "fail", "uncertain"]

class MockWorkerCoachAdapter:
    """
    Adapter for worker coach service.
    Supports both explicit mock verdict selection for deterministic tests and demonstrations,
    and a separate content evaluation path that inspects actual step criteria and photo assets.
    """

    def __init__(
        self,
        contentResolver: Optional[ContentResolver] = None,
        visionEvaluator: Optional[VisionEvaluator] = None
    ) -> None:
        self.contentResolver = contentResolver or LocalContentResolver()
        self.visionEvaluator = visionEvaluator or MockCriteriaVisionEvaluator()

    def evaluateCheckpoint(
        self,
        request: Dict[str, Any],
        verdict: MockVerdict = "pass"
    ) -> Dict[str, Any]:
        """
        Explicit mock evaluation path for regression testing and demonstrations.
        """
        validReq, reqError = validateSchema("checkpointRequest", request)
        if not validReq:
            raise ValueError(f"Invalid checkpoint request: {reqError}")

        if verdict not in ("pass", "fail", "uncertain"):
            raise ValueError(f"Unsupported mock verdict: {verdict}")

        sessionId = request["sessionId"]
        stepId = request["stepId"]

        if verdict == "pass":
            result = {
                "schemaVersion": 1,
                "checkpointId": f"chk-{stepId}-pass",
                "sessionId": sessionId,
                "stepId": stepId,
                "verdict": "pass",
                "confidence": 0.94,
                "observed": ["ceramic mug", "double bubble wrap"],
                "missing": [],
                "message": "Protection verified with double layer cushioning",
                "correction": None
            }
        elif verdict == "fail":
            result = {
                "schemaVersion": 1,
                "checkpointId": f"chk-{stepId}-fail",
                "sessionId": sessionId,
                "stepId": stepId,
                "verdict": "fail",
                "confidence": 0.91,
                "observed": ["ceramic mug", "single bubble wrap"],
                "missing": ["second bubble wrap layer"],
                "message": "Only single layer bubble wrap detected",
                "correction": "Add a second complete layer of bubble wrap before boxing"
            }
        else:
            result = {
                "schemaVersion": 1,
                "checkpointId": f"chk-{stepId}-unc",
                "sessionId": sessionId,
                "stepId": stepId,
                "verdict": "uncertain",
                "confidence": 0.42,
                "observed": ["ceramic mug"],
                "missing": [],
                "message": "Image is blurry or obstructed, please capture another photo",
                "correction": "Hold camera steady with proper lighting and retake"
            }

        validResult, resultError = validateSchema("checkpointResult", result)
        if not validResult:
            raise ValueError(f"Generated checkpoint result failed schema validation: {resultError}")

        return result

    def evaluateRequestContent(
        self,
        request: Dict[str, Any],
        imageBytes: Optional[bytes] = None,
        referenceImageBytes: Optional[bytes] = None
    ) -> Dict[str, Any]:
        """
        Content evaluation path resolving approved step criteria and image bytes.
        """
        validReq, reqError = validateSchema("checkpointRequest", request)
        if not validReq:
            raise ValueError(f"Invalid checkpoint request: {reqError}")

        sessionId = request["sessionId"]
        stepId = request["stepId"]
        imageKey = request["checkpointImageKey"]

        # Resolve step criteria strictly from approved version
        stepCriteria = self.contentResolver.resolveApprovedStep(stepId, sessionId=sessionId)
        if stepCriteria is None:
            raise ValueError(f"Cannot evaluate checkpoint for unknown or unapproved step: {stepId}")

        # Resolve image bytes if not directly provided
        actualImageBytes = imageBytes if imageBytes is not None else self.contentResolver.resolveImageBytes(imageKey)
        if not actualImageBytes:
            # A missing or nonexistent image key must never pass
            result = {
                "schemaVersion": 1,
                "checkpointId": f"chk-{stepId}-uncertain",
                "sessionId": sessionId,
                "stepId": stepId,
                "verdict": "uncertain",
                "confidence": 0.0,
                "observed": [],
                "missing": [],
                "message": f"Checkpoint image is missing or unreachable: {imageKey}",
                "correction": "Hold camera steady and capture required checkpoint photo"
            }
            validResult, resultError = validateSchema("checkpointResult", result)
            if not validResult:
                raise ValueError(f"Generated checkpoint result failed schema validation: {resultError}")
            return result

        evaluation = self.visionEvaluator.evaluateImage(
            imageBytes=actualImageBytes,
            stepCriteria=stepCriteria,
            referenceImageBytes=referenceImageBytes
        )

        result = {
            "schemaVersion": 1,
            "checkpointId": f"chk-{stepId}-{evaluation.verdict}",
            "sessionId": sessionId,
            "stepId": stepId,
            "verdict": evaluation.verdict,
            "confidence": evaluation.confidence,
            "observed": evaluation.observed,
            "missing": evaluation.missing,
            "message": evaluation.message,
            "correction": evaluation.correction
        }

        validResult, resultError = validateSchema("checkpointResult", result)
        if not validResult:
            raise ValueError(f"Generated checkpoint result failed schema validation: {resultError}")

        return result
