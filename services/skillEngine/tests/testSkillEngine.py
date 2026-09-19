import json
from pathlib import Path
import pytest
from skillEngine.mockAdapter import MockSkillEngineAdapter
from skillEngine.validator import validateSchema, validateActionOrder

def getFixturePath(filename: str) -> Path:
    repoRoot = Path(__file__).resolve().parent.parent.parent.parent
    return repoRoot / "packages" / "contracts" / "fixtures" / filename

def testComposeDraftProducesValidSixStepPackage() -> None:
    bundlePath = getFixturePath("evidenceBundle.valid.json")
    with open(bundlePath, "r", encoding="utf-8") as f:
        bundle = json.load(f)

    adapter = MockSkillEngineAdapter()
    draft = adapter.composeDraft(bundle)

    assert draft["schemaVersion"] == 1
    assert draft["skillId"] == bundle["skillId"]
    assert draft["status"] == "reviewRequired"
    assert draft["version"] == 0
    assert draft["approvedBy"] is None
    assert draft["approvedAt"] is None
    assert len(draft["steps"]) == 6

    validDraft, error = validateSchema("skillPackage", draft)
    assert validDraft, f"Draft schema error: {error}"
    assert validateActionOrder(draft["steps"])

def testDeliberateConflictIsPreservedOnProtectionStep() -> None:
    bundlePath = getFixturePath("evidenceBundle.valid.json")
    with open(bundlePath, "r", encoding="utf-8") as f:
        bundle = json.load(f)

    adapter = MockSkillEngineAdapter()
    draft = adapter.composeDraft(bundle)

    step3 = draft["steps"][2]
    assert step3["actionCode"] == "addProtection"
    assert step3["policyStatus"] == "conflict"
    assert step3["warning"] == "Demonstration shows single wrap but policy requires two layers"
    assert step3["policyCitation"] is not None
    assert step3["policyCitation"]["page"] == 4
    assert step3["checkpointRequired"] is True
    assert "obs-003" in step3["evidenceObservationIds"]

def testComposeDraftFailsOnInvalidEvidenceBundle() -> None:
    bundlePath = getFixturePath("evidenceBundle.invalidActionCode.invalid.json")
    with open(bundlePath, "r", encoding="utf-8") as f:
        bundle = json.load(f)

    adapter = MockSkillEngineAdapter()
    with pytest.raises(ValueError):
        adapter.composeDraft(bundle)
