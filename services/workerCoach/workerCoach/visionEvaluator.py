import io
from typing import Any, Dict, List, Optional
from PIL import Image, ImageStat

class VisionEvaluationResult:
    def __init__(
        self,
        verdict: str,
        confidence: float,
        observed: List[str],
        missing: List[str],
        message: str,
        correction: Optional[str] = None
    ) -> None:
        self.verdict = verdict
        self.confidence = confidence
        self.observed = observed
        self.missing = missing
        self.message = message
        self.correction = correction

class VisionEvaluator:
    def evaluateImage(
        self,
        imageBytes: bytes,
        stepCriteria: Dict[str, Any],
        referenceImageBytes: Optional[bytes] = None
    ) -> VisionEvaluationResult:
        raise NotImplementedError("Subclasses must implement evaluateImage")

class MockCriteriaVisionEvaluator(VisionEvaluator):
    """
    Explicit test double using byte markers for deterministic unit tests.
    """

    def evaluateImage(
        self,
        imageBytes: bytes,
        stepCriteria: Dict[str, Any],
        referenceImageBytes: Optional[bytes] = None
    ) -> VisionEvaluationResult:
        if not imageBytes or len(imageBytes) < 10:
            return VisionEvaluationResult(
                verdict="uncertain",
                confidence=0.1,
                observed=[],
                missing=[],
                message="Unreadable or empty image file, please capture another photo",
                correction="Ensure camera lens is clean and retake photo"
            )

        if b"blurry" in imageBytes or b"blur" in imageBytes or b"unclear" in imageBytes:
            return VisionEvaluationResult(
                verdict="uncertain",
                confidence=0.42,
                observed=["ceramic mug"],
                missing=[],
                message="Image is blurry or obstructed, please capture another photo",
                correction="Hold camera steady with proper lighting and retake"
            )

        if b"single" in imageBytes:
            return VisionEvaluationResult(
                verdict="fail",
                confidence=0.91,
                observed=["ceramic mug", "single bubble wrap"],
                missing=["second bubble wrap layer"],
                message="Only single layer bubble wrap detected",
                correction="Add a second complete layer of bubble wrap before boxing"
            )

        return VisionEvaluationResult(
            verdict="pass",
            confidence=0.94,
            observed=["ceramic mug", "double bubble wrap"],
            missing=[],
            message="Protection verified with double layer cushioning",
            correction=None
        )

class LocalCriteriaVisionEvaluator(VisionEvaluator):
    """
    Real pixel based checkpoint evaluator.
    Fails closed: blank, uniform, blurry, or uninformative photos return uncertain.
    Never returns pass without positive visual evidence of compliance.
    """

    def evaluateImage(
        self,
        imageBytes: bytes,
        stepCriteria: Dict[str, Any],
        referenceImageBytes: Optional[bytes] = None
    ) -> VisionEvaluationResult:
        if not imageBytes or len(imageBytes) < 32:
            return VisionEvaluationResult(
                verdict="uncertain",
                confidence=0.1,
                observed=[],
                missing=[],
                message="Empty or corrupt image file, please capture another photo",
                correction="Ensure camera lens is clean and retake photo"
            )

        # Decode actual pixel stream
        try:
            img = Image.open(io.BytesIO(imageBytes)).convert("RGB")
        except Exception:
            return VisionEvaluationResult(
                verdict="uncertain",
                confidence=0.15,
                observed=[],
                missing=[],
                message="Unrecognized image format or corrupt file",
                correction="Hold camera steady and retake photo in supported JPEG format"
            )

        # Compute image statistics across color channels
        stat = ImageStat.Stat(img)
        avgStddev = sum(stat.stddev) / len(stat.stddev)

        # Fail closed on blank, solid color, or underexposed photos
        if avgStddev < 8.0:
            return VisionEvaluationResult(
                verdict="uncertain",
                confidence=0.12,
                observed=[],
                missing=[],
                message="Blank or uninformative photo, please capture another photo",
                correction="Aim camera at packaging bench under proper lighting and retake"
            )

        # Real checkpoint mode requires positive visual evidence from vision provider or template
        # Without multimodal verification, an ordinary or irrelevant photo cannot pass
        actionCode = stepCriteria.get("actionCode", "")

        return VisionEvaluationResult(
            verdict="uncertain",
            confidence=0.35,
            observed=[],
            missing=[f"verified visual evidence for {actionCode}"],
            message=f"Visual evidence for {actionCode} cannot be verified without vision provider",
            correction="Ensure camera is focused on packaging bench and retake"
        )
