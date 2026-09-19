import json
from pathlib import Path
import pytest
from workerCoach.mockAdapter import MockWorkerCoachAdapter
from workerCoach.validator import validateSchema

def getFixturePath(filename: str) -> Path:
    repoRoot = Path(__file__).resolve().parent.parent.parent.parent
    return repoRoot / "packages" / "contracts" / "fixtures" / filename

def testEvaluateCheckpointPass() -> None:
    reqPath = getFixturePath("checkpointRequest.valid.json")
    with open(reqPath, "r", encoding="utf-8") as f:
        request = json.load(f)

    adapter = MockWorkerCoachAdapter()
    result = adapter.evaluateCheckpoint(request, verdict="pass")

    assert result["verdict"] == "pass"
    assert result["sessionId"] == request["sessionId"]
    assert result["stepId"] == request["stepId"]
    assert result["confidence"] >= 0.9
    assert result["correction"] is None

    valid, error = validateSchema("checkpointResult", result)
    assert valid, f"Result schema error: {error}"

def testEvaluateCheckpointFail() -> None:
    reqPath = getFixturePath("checkpointRequest.valid.json")
    with open(reqPath, "r", encoding="utf-8") as f:
        request = json.load(f)

    adapter = MockWorkerCoachAdapter()
    result = adapter.evaluateCheckpoint(request, verdict="fail")

    assert result["verdict"] == "fail"
    assert result["correction"] is not None
    assert len(result["missing"]) > 0

    valid, error = validateSchema("checkpointResult", result)
    assert valid, f"Result schema error: {error}"

def testEvaluateCheckpointUncertain() -> None:
    reqPath = getFixturePath("checkpointRequest.valid.json")
    with open(reqPath, "r", encoding="utf-8") as f:
        request = json.load(f)

    adapter = MockWorkerCoachAdapter()
    result = adapter.evaluateCheckpoint(request, verdict="uncertain")

    assert result["verdict"] == "uncertain"
    assert result["confidence"] < 0.5
    assert result["correction"] is not None

    valid, error = validateSchema("checkpointResult", result)
    assert valid, f"Result schema error: {error}"

def testEvaluateCheckpointInvalidRequestFails() -> None:
    adapter = MockWorkerCoachAdapter()
    with pytest.raises(ValueError):
        adapter.evaluateCheckpoint({"invalid": "data"}, verdict="pass")
