from typing import Any, Dict, Literal
from .validator import validateSchema

MockVerdict = Literal["pass", "fail", "uncertain"]

class MockWorkerCoachAdapter:
    """
    Deterministic mock adapter for worker coach.
    Does not run live computer vision models.
    Produces explicit pass, fail, or uncertain verification results based on selection.
    """

    def evaluateCheckpoint(
        self,
        request: Dict[str, Any],
        verdict: MockVerdict = "pass"
    ) -> Dict[str, Any]:
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
