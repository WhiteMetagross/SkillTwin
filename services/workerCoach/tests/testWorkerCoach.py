import io
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from workerCoach.bedrockVisionEvaluator import BedrockVisionEvaluator
from workerCoach.contentResolver import LocalContentResolver
from workerCoach.mockAdapter import MockWorkerCoachAdapter
from workerCoach.validator import validateSchema
from workerCoach.visionEvaluator import LocalCriteriaVisionEvaluator

def getFixturePath(filename: str) -> Path:
    repoRoot = Path(__file__).resolve().parent.parent.parent.parent
    return repoRoot / "packages" / "contracts" / "fixtures" / filename

def getAssetPath(filename: str) -> Path:
    return Path(__file__).resolve().parent / "assets" / filename

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

def testContentEvaluationPassWithDoubleWrap() -> None:
    reqPath = getFixturePath("checkpointRequest.valid.json")
    with open(reqPath, "r", encoding="utf-8") as f:
        request = json.load(f)

    imgBytes = getAssetPath("correct_double_wrap.jpg").read_bytes()
    adapter = MockWorkerCoachAdapter()
    result = adapter.evaluateRequestContent(request, imageBytes=imgBytes)

    assert result["verdict"] == "pass"
    assert result["confidence"] >= 0.9
    assert result["correction"] is None
    assert "double bubble wrap" in result["observed"]

    valid, error = validateSchema("checkpointResult", result)
    assert valid, f"Result schema error: {error}"

def testContentEvaluationFailWithSingleWrap() -> None:
    reqPath = getFixturePath("checkpointRequest.valid.json")
    with open(reqPath, "r", encoding="utf-8") as f:
        request = json.load(f)

    imgBytes = getAssetPath("single_wrap_fail.jpg").read_bytes()
    adapter = MockWorkerCoachAdapter()
    result = adapter.evaluateRequestContent(request, imageBytes=imgBytes)

    assert result["verdict"] == "fail"
    assert result["correction"] is not None
    assert "second bubble wrap layer" in result["missing"]
    assert "single" in result["message"]

    valid, error = validateSchema("checkpointResult", result)
    assert valid, f"Result schema error: {error}"

def testContentEvaluationUncertainWithBlurryPhoto() -> None:
    reqPath = getFixturePath("checkpointRequest.valid.json")
    with open(reqPath, "r", encoding="utf-8") as f:
        request = json.load(f)

    imgBytes = getAssetPath("blurry_unclear.jpg").read_bytes()
    adapter = MockWorkerCoachAdapter()
    result = adapter.evaluateRequestContent(request, imageBytes=imgBytes)

    assert result["verdict"] == "uncertain"
    assert result["confidence"] < 0.5
    assert result["correction"] is not None
    assert "blurry" in result["message"]

    valid, error = validateSchema("checkpointResult", result)
    assert valid, f"Result schema error: {error}"

def testContentEvaluationUncertainWithCorruptImage() -> None:
    reqPath = getFixturePath("checkpointRequest.valid.json")
    with open(reqPath, "r", encoding="utf-8") as f:
        request = json.load(f)

    imgBytes = getAssetPath("corrupt_image.jpg").read_bytes()
    adapter = MockWorkerCoachAdapter()
    result = adapter.evaluateRequestContent(request, imageBytes=imgBytes)

    assert result["verdict"] == "uncertain"
    assert result["confidence"] < 0.5
    assert result["correction"] is not None

    valid, error = validateSchema("checkpointResult", result)
    assert valid, f"Result schema error: {error}"

def testContentEvaluationWithEmptyBytes() -> None:
    reqPath = getFixturePath("checkpointRequest.valid.json")
    with open(reqPath, "r", encoding="utf-8") as f:
        request = json.load(f)

    adapter = MockWorkerCoachAdapter()
    result = adapter.evaluateRequestContent(request, imageBytes=b"")

    assert result["verdict"] == "uncertain"
    assert result["confidence"] < 0.5

    valid, error = validateSchema("checkpointResult", result)
    assert valid, f"Result schema error: {error}"

def testBedrockVisionEvaluatorMockSuccess() -> None:
    mockBedrock = MagicMock()
    modelOutput = {
        "content": [
            {
                "type": "text",
                "text": json.dumps({
                    "verdict": "pass",
                    "confidence": 0.96,
                    "observed": ["ceramic mug", "double bubble wrap"],
                    "missing": [],
                    "message": "Double wrap verified by Bedrock",
                    "correction": None
                })
            }
        ]
    }
    mockResponse = {
        "body": io.BytesIO(json.dumps(modelOutput).encode("utf-8"))
    }
    mockBedrock.invoke_model.return_value = mockResponse

    evaluator = BedrockVisionEvaluator(bedrockClient=mockBedrock)
    dummyBytes = getAssetPath("correct_double_wrap.jpg").read_bytes()
    criteria = {
        "actionCode": "addProtection",
        "instruction": "Wrap fragile item with two complete layers of bubble wrap"
    }

    result = evaluator.evaluateImage(dummyBytes, criteria)
    assert result.verdict == "pass"
    assert result.confidence == 0.96
    assert "double bubble wrap" in result.observed
    assert result.correction is None

def testBedrockVisionEvaluatorMalformedFallback() -> None:
    mockBedrock = MagicMock()
    badOutput = {
        "content": [
            {
                "type": "text",
                "text": "This is raw unstructured text without json"
            }
        ]
    }
    mockResponse = {
        "body": io.BytesIO(json.dumps(badOutput).encode("utf-8"))
    }
    mockBedrock.invoke_model.return_value = mockResponse

    localFallback = LocalCriteriaVisionEvaluator()
    evaluator = BedrockVisionEvaluator(
        bedrockClient=mockBedrock,
        fallbackEvaluator=localFallback
    )
    dummyBytes = getAssetPath("correct_double_wrap.jpg").read_bytes()
    criteria = {
        "actionCode": "addProtection",
        "instruction": "Wrap fragile item with two complete layers of bubble wrap"
    }

    result = evaluator.evaluateImage(dummyBytes, criteria)
    assert result.verdict == "pass"
    assert result.confidence >= 0.9

def testBedrockVisionEvaluatorClientExceptionFallback() -> None:
    mockBedrock = MagicMock()
    mockBedrock.invoke_model.side_effect = RuntimeError("AWS Bedrock service error")

    localFallback = LocalCriteriaVisionEvaluator()
    evaluator = BedrockVisionEvaluator(
        bedrockClient=mockBedrock,
        fallbackEvaluator=localFallback
    )
    dummyBytes = getAssetPath("single_wrap_fail.jpg").read_bytes()
    criteria = {
        "actionCode": "addProtection",
        "instruction": "Wrap fragile item with two complete layers of bubble wrap"
    }

    result = evaluator.evaluateImage(dummyBytes, criteria)
    assert result.verdict == "fail"
    assert "second bubble wrap layer" in result.missing

def testLocalContentResolver() -> None:
    resolver = LocalContentResolver()
    step003 = resolver.resolveApprovedStep("step-003")
    assert step003 is not None
    assert step003["actionCode"] == "addProtection"

    unknownStep = resolver.resolveApprovedStep("step-999")
    assert unknownStep is None

    fallbackImg = resolver.resolveImageBytes("nonexistent-key")
    assert fallbackImg.startswith(b"\xff\xd8\xff")
