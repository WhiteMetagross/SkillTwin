import io
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from skillEngine.audioService import AmazonPollyService, LocalAudioSynthesisService
from skillEngine.bedrockCaller import BedrockModelCaller
from skillEngine.mockAdapter import MockSkillEngineAdapter
from skillEngine.modelCaller import LocalModelCaller, ModelCompositionResult
from skillEngine.observationMapper import mapObservationsToActionSlots
from skillEngine.policyExtractor import PdfPolicyExtractor, PolicyIndex
from skillEngine.policyVerifier import PolicyVerifier
from skillEngine.textractExtractor import TextractPolicyExtractor
from skillEngine.translationService import AmazonTranslateService, LocalTranslationService
from skillEngine.validator import validateActionOrder, validateSchema

def getFixturePath(filename: str) -> Path:
    repoRoot = Path(__file__).resolve().parent.parent.parent.parent
    return repoRoot / "packages" / "contracts" / "fixtures" / filename

def getAssetPath(filename: str) -> Path:
    return Path(__file__).resolve().parent / "assets" / filename

def testSixActionOrderAndSchemaValidity() -> None:
    bundlePath = getFixturePath("evidenceBundle.valid.json")
    with open(bundlePath, "r", encoding="utf-8") as f:
        bundle = json.load(f)

    adapter = MockSkillEngineAdapter()
    draft = adapter.composeDraft(bundle)

    assert draft["schemaVersion"] == 1
    assert draft["status"] == "reviewRequired"
    assert draft["version"] == 0
    assert draft["approvedBy"] is None
    assert draft["approvedAt"] is None
    assert len(draft["steps"]) == 6

    validDraft, error = validateSchema("skillPackage", draft)
    assert validDraft, f"Draft schema error: {error}"
    assert validateActionOrder(draft["steps"])

def testRepeatedActionsFromTwoVideosMerged() -> None:
    # Bundle with repeated observations across two videos for selectBox
    repeatedBundle = {
        "schemaVersion": 1,
        "skillId": "skill-repeated-001",
        "videos": [
            {"videoId": "video-001", "hasNarration": True, "transcriptKey": None},
            {"videoId": "video-002", "hasNarration": False, "transcriptKey": None}
        ],
        "observations": [
            {
                "observationId": "obs-prod-1",
                "videoId": "video-001",
                "startMs": 1000,
                "endMs": 4000,
                "beforeState": "shelf",
                "action": "inspect item",
                "afterState": "table",
                "visibleObjects": ["ceramic mug"],
                "spokenEvidence": "Inspect mug",
                "candidateAction": "selectProduct",
                "referenceFrameKey": "skills/s1/frames/v1/2000.jpg",
                "confidence": 0.90
            },
            {
                "observationId": "obs-box-v1",
                "videoId": "video-001",
                "startMs": 4500,
                "endMs": 7000,
                "beforeState": "cartons",
                "action": "fold carton",
                "afterState": "open box",
                "visibleObjects": ["cardboard box"],
                "spokenEvidence": None,
                "candidateAction": "selectBox",
                "referenceFrameKey": "skills/s1/frames/v1/5000.jpg",
                "confidence": 0.85
            },
            {
                "observationId": "obs-box-v2",
                "videoId": "video-002",
                "startMs": 1000,
                "endMs": 5000,
                "beforeState": "cartons",
                "action": "assemble carton with precision",
                "afterState": "assembled box",
                "visibleObjects": ["cardboard box"],
                "spokenEvidence": None,
                "candidateAction": "selectBox",
                "referenceFrameKey": "skills/s1/frames/v2/3000.jpg",
                "confidence": 0.96
            },
            {
                "observationId": "obs-prot-1",
                "videoId": "video-001",
                "startMs": 7500,
                "endMs": 12000,
                "beforeState": "bare",
                "action": "wrap with bubble sheet",
                "afterState": "wrapped",
                "visibleObjects": ["ceramic mug", "bubble wrap"],
                "spokenEvidence": None,
                "candidateAction": "addProtection",
                "referenceFrameKey": "skills/s1/frames/v1/9000.jpg",
                "confidence": 0.88
            },
            {
                "observationId": "obs-place-1",
                "videoId": "video-001",
                "startMs": 13000,
                "endMs": 17000,
                "beforeState": "wrapped",
                "action": "place mug in box",
                "afterState": "mug in box",
                "visibleObjects": ["cardboard box"],
                "spokenEvidence": None,
                "candidateAction": "placeProduct",
                "referenceFrameKey": "skills/s1/frames/v1/15000.jpg",
                "confidence": 0.92
            },
            {
                "observationId": "obs-seal-1",
                "videoId": "video-001",
                "startMs": 18000,
                "endMs": 22000,
                "beforeState": "open",
                "action": "tape box",
                "afterState": "sealed",
                "visibleObjects": ["cardboard box", "tape"],
                "spokenEvidence": None,
                "candidateAction": "sealBox",
                "referenceFrameKey": "skills/s1/frames/v1/20000.jpg",
                "confidence": 0.95
            },
            {
                "observationId": "obs-label-1",
                "videoId": "video-001",
                "startMs": 23000,
                "endMs": 26000,
                "beforeState": "unlabeled",
                "action": "apply label",
                "afterState": "labeled",
                "visibleObjects": ["cardboard box", "fragile label"],
                "spokenEvidence": None,
                "candidateAction": "attachLabel",
                "referenceFrameKey": "skills/s1/frames/v1/24000.jpg",
                "confidence": 0.97
            }
        ]
    }

    adapter = MockSkillEngineAdapter()
    draft = adapter.composeDraft(repeatedBundle)

    stepBox = draft["steps"][1]
    assert stepBox["actionCode"] == "selectBox"
    # Should choose representative with higher confidence (obs-box-v2 from video-002)
    assert stepBox["sourceVideoId"] == "video-002"
    assert stepBox["confidence"] == 0.96
    # Traceability must include all matching observation IDs
    assert "obs-box-v1" in stepBox["evidenceObservationIds"]
    assert "obs-box-v2" in stepBox["evidenceObservationIds"]
    assert len(stepBox["evidenceObservationIds"]) == 2

def testMissingActionSlotMarkedNeedsReview() -> None:
    # Bundle missing attachLabel action
    partialBundle = {
        "schemaVersion": 1,
        "skillId": "skill-missing-001",
        "videos": [
            {"videoId": "video-001", "hasNarration": False, "transcriptKey": None}
        ],
        "observations": [
            {
                "observationId": "obs-1",
                "videoId": "video-001",
                "startMs": 1000,
                "endMs": 4000,
                "beforeState": "bench",
                "action": "inspect item",
                "afterState": "inspected",
                "visibleObjects": ["ceramic mug"],
                "spokenEvidence": None,
                "candidateAction": "selectProduct",
                "referenceFrameKey": "skills/s/frames/2000.jpg",
                "confidence": 0.90
            }
        ]
    }

    adapter = MockSkillEngineAdapter()
    draft = adapter.composeDraft(partialBundle)

    assert len(draft["steps"]) == 6
    missingStep = draft["steps"][5]
    assert missingStep["actionCode"] == "attachLabel"
    assert missingStep["policyStatus"] == "needsReview"
    assert missingStep["sourceVideoId"] is None
    assert missingStep["startMs"] is None
    assert missingStep["endMs"] is None
    assert missingStep["referenceFrameKey"] is None
    assert missingStep["confidence"] is None
    assert missingStep["evidenceObservationIds"] == []
    assert missingStep["warning"] is not None

def testInvalidInputBundleRejected() -> None:
    adapter = MockSkillEngineAdapter()
    with pytest.raises(ValueError):
        adapter.composeDraft({"schemaVersion": 1, "invalidField": True})

def testPolicyExtractionFromRealPdf() -> None:
    pdfPath = getAssetPath("samplePolicy.pdf")
    assert pdfPath.is_file(), "samplePolicy.pdf fixture missing"

    content = pdfPath.read_bytes()
    extractor = PdfPolicyExtractor()
    doc = extractor.extractDocument("doc-packing-policy-001", content)

    assert doc.documentId == "doc-packing-policy-001"
    assert len(doc.sections) >= 5

    index = PolicyIndex()
    index.indexDocument(doc)

    citationProtection = index.findCitation("addProtection")
    assert citationProtection is not None
    assert citationProtection["documentId"] == "doc-packing-policy-001"
    assert citationProtection["page"] == 4
    assert "Cushioning" in citationProtection["section"] or "cushioning" in citationProtection["section"].lower()
    assert "two complete layers" in citationProtection["excerpt"].lower()

def testDeliberateConflictOnProtectionStep() -> None:
    bundlePath = getFixturePath("evidenceBundle.valid.json")
    with open(bundlePath, "r", encoding="utf-8") as f:
        bundle = json.load(f)

    adapter = MockSkillEngineAdapter()
    draft = adapter.composeDraft(bundle)

    step3 = draft["steps"][2]
    assert step3["actionCode"] == "addProtection"
    assert step3["policyStatus"] == "conflict"
    assert "single wrap but policy requires two layers" in step3["warning"]
    assert step3["policyCitation"] is not None
    assert step3["policyCitation"]["page"] == 4

def testNoPolicyDocumentResultsInNotFound() -> None:
    bundlePath = getFixturePath("evidenceBundle.valid.json")
    with open(bundlePath, "r", encoding="utf-8") as f:
        bundle = json.load(f)

    adapter = MockSkillEngineAdapter()
    # Pass empty citations mapping
    emptyCitations = {action: None for action in ["selectProduct", "selectBox", "addProtection", "placeProduct", "sealBox", "attachLabel"]}
    draft = adapter.composeDraft(bundle, customCitations=emptyCitations)

    step1 = draft["steps"][0]
    assert step1["policyStatus"] == "notFound"
    assert step1["policyCitation"] is None

def testBedrockModelCallerSuccessAndFallback() -> None:
    mockClient = MagicMock()
    modelJson = {
        "title": "Pack fragile item",
        "materials": ["ceramic mug", "cardboard box"],
        "prerequisites": ["clean bench"],
        "instructions": {
            "selectProduct": "Inspect product carefully.",
            "selectBox": "Assemble box.",
            "addProtection": "Wrap with bubble wrap.",
            "placeProduct": "Place item inside box.",
            "sealBox": "Seal box seams.",
            "attachLabel": "Apply fragile label."
        }
    }

    mockResponse = {
        "body": io.BytesIO(json.dumps({
            "content": [{"type": "text", "text": json.dumps(modelJson)}]
        }).encode("utf-8"))
    }
    mockClient.invoke_model.return_value = mockResponse

    bedrockCaller = BedrockModelCaller(bedrockClient=mockClient)
    res = bedrockCaller.composeSkillContent("s1", {}, {})

    assert res.title == "Pack fragile item"
    assert "ceramic mug" in res.materials

    # Test malformed model response triggers safe local fallback
    badResponse = {
        "body": io.BytesIO(b"malformed non json text")
    }
    mockClient.invoke_model.return_value = badResponse
    fallbackRes = bedrockCaller.composeSkillContent("s1", {}, {})
    assert fallbackRes.title.startswith("Pack")

def testTextractPolicyExtractorMockedSdk() -> None:
    mockClient = MagicMock()
    mockClient.detect_document_text.return_value = {
        "Blocks": [
            {"BlockType": "PAGE", "Page": 1},
            {"BlockType": "LINE", "Page": 1, "Text": "CUSHIONING REQUIREMENTS"},
            {"BlockType": "LINE", "Page": 1, "Text": "Fragile items require two layers of bubble wrap."}
        ]
    }

    extractor = TextractPolicyExtractor(textractClient=mockClient)
    doc = extractor.extractDocument("doc-scanned-001", b"fake_pdf_bytes")

    assert doc.documentId == "doc-scanned-001"
    assert len(doc.sections) == 1
    assert doc.sections[0].page == 1
    assert "two layers" in doc.sections[0].text

def testApprovedOnlyTranslation() -> None:
    bundlePath = getFixturePath("evidenceBundle.valid.json")
    with open(bundlePath, "r", encoding="utf-8") as f:
        bundle = json.load(f)

    adapter = MockSkillEngineAdapter()
    draft = adapter.composeDraft(bundle)

    translator = LocalTranslationService()

    # Draft must be rejected
    with pytest.raises(ValueError, match="Draft skills cannot be translated"):
        translator.translateApprovedSkill(draft)

    # Approved skill succeeds
    approvedSkill = {
        **draft,
        "status": "approved",
        "version": 1,
        "approvedBy": "supervisor-jane"
    }
    translations = translator.translateApprovedSkill(approvedSkill, targetLanguage="hiIN")
    assert len(translations) == 6
    assert "step-001" in translations

def testAmazonTranslateServiceMockedSdk() -> None:
    mockClient = MagicMock()
    mockClient.translate_text.return_value = {
        "TranslatedText": "उत्पाद का निरीक्षण करें"
    }

    translator = AmazonTranslateService(translateClient=mockClient)
    approvedSkill = {
        "status": "approved",
        "version": 1,
        "approvedBy": "supervisor-jane",
        "steps": [
            {"stepId": "step-001", "instruction": "Inspect product"}
        ]
    }

    res = translator.translateApprovedSkill(approvedSkill, targetLanguage="hiIN")
    assert res["step-001"] == "उत्पाद का निरीक्षण करें"

def testApprovedOnlyAudioSynthesis() -> None:
    bundlePath = getFixturePath("evidenceBundle.valid.json")
    with open(bundlePath, "r", encoding="utf-8") as f:
        bundle = json.load(f)

    adapter = MockSkillEngineAdapter()
    draft = adapter.composeDraft(bundle)

    audioService = LocalAudioSynthesisService()

    # Draft must be rejected
    with pytest.raises(ValueError, match="Draft skills cannot synthesize audio"):
        audioService.synthesizeApprovedSkillAudio(draft)

    # Approved skill succeeds
    approvedSkill = {
        **draft,
        "status": "approved",
        "version": 1,
        "approvedBy": "supervisor-jane"
    }
    descriptors = audioService.synthesizeApprovedSkillAudio(approvedSkill, language="hiIN")
    assert len(descriptors) == 6
    assert "step-001" in descriptors
    desc = descriptors["step-001"]
    assert "skills/skill-fragile-mug-001/versions/v1/audio/hiIN/step-001.mp3" in desc.storageKey

def testAmazonPollyServiceMockedSdk() -> None:
    mockClient = MagicMock()
    mockClient.synthesize_speech.return_value = {
        "AudioStream": io.BytesIO(b"fake_mp3_stream")
    }

    polly = AmazonPollyService(pollyClient=mockClient)
    approvedSkill = {
        "skillId": "skill-test-01",
        "status": "approved",
        "version": 1,
        "approvedBy": "supervisor-jane",
        "steps": [
            {"stepId": "step-001", "instruction": "Inspect product", "instructionHi": "उत्पाद जांचें"}
        ]
    }

    res = polly.synthesizeApprovedSkillAudio(approvedSkill, language="hiIN")
    assert "step-001" in res
    assert res["step-001"].storageKey == "skills/skill-test-01/versions/v1/audio/hiIN/step-001.mp3"
