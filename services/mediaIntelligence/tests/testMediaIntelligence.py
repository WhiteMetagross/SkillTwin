import json
from pathlib import Path
import pytest
from mediaIntelligence.mockAdapter import MockMediaIntelligenceAdapter
from mediaIntelligence.validator import validateSchema

def getFixturePath(filename: str) -> Path:
    repoRoot = Path(__file__).resolve().parent.parent.parent.parent
    return repoRoot / "packages" / "contracts" / "fixtures" / filename

def testProcessValidManifestProducesValidEvidenceBundle() -> None:
    manifestPath = getFixturePath("assetManifest.valid.json")
    with open(manifestPath, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    adapter = MockMediaIntelligenceAdapter()
    bundle = adapter.processManifest(manifest)

    assert bundle["schemaVersion"] == 1
    assert bundle["skillId"] == manifest["skillId"]
    assert len(bundle["videos"]) == 2
    assert len(bundle["observations"]) == 6

    valid, error = validateSchema("evidenceBundle", bundle)
    assert valid, f"Evidence bundle schema error: {error}"

def testProcessInvalidManifestFails() -> None:
    manifestPath = getFixturePath("assetManifest.unknownField.invalid.json")
    with open(manifestPath, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    adapter = MockMediaIntelligenceAdapter()
    with pytest.raises(ValueError):
        adapter.processManifest(manifest)

def testAllObservationsHaveOrderedTimestamps() -> None:
    manifestPath = getFixturePath("assetManifest.valid.json")
    with open(manifestPath, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    adapter = MockMediaIntelligenceAdapter()
    bundle = adapter.processManifest(manifest)

    for obs in bundle["observations"]:
        assert obs["endMs"] > obs["startMs"]
        assert obs["confidence"] >= 0.0
        assert obs["confidence"] <= 1.0
