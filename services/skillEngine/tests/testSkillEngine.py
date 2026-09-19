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
    assert stepBox["sourceVideoId"] == "video-002"
    assert stepBox["confidence"] == 0.96
    assert "obs-box-v1" in stepBox["evidenceObservationIds"]
    assert "obs-box-v2" in stepBox["evidenceObservationIds"]
    assert len(stepBox["evidenceObservationIds"]) == 2

def testMissingActionSlotMarkedNeedsReview() -> None:
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

def testMalformedPdfInputRaisesValueError() -> None:
    extractor = PdfPolicyExtractor()

    # Case 1: Arbitrary non PDF bytes
    with pytest.raises(ValueError, match="Invalid PDF header|corrupted PDF"):
        extractor.extractDocument("bad-doc", b"not_a_valid_pdf_stream_garbage_bytes")

    # Case 2: Empty bytes
    with pytest.raises(ValueError, match="Empty or corrupted PDF"):
        extractor.extractDocument("empty-doc", b"")

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
    emptyCitations = {action: None for action in ["selectProduct", "selectBox", "addProtection", "placeProduct", "sealBox", "attachLabel"]}
    draft = adapter.composeDraft(bundle, customCitations=emptyCitations)

    step1 = draft["steps"][0]
    assert step1["policyStatus"] == "notFound"
    assert step1["policyCitation"] is None

def testBedrockCompositionPromptContainsObservationFactsAndPolicyCitations() -> None:
    mockClient = MagicMock()
    modelJson = {
        "title": "Pack fragile item",
        "materials": ["ceramic mug", "cardboard box", "bubble wrap"],
        "prerequisites": ["clean bench"],
        "instructions": {
            "selectProduct": "Inspect product carefully.",
            "selectBox": "Assemble box.",
            "addProtection": "Wrap with two layers of bubble wrap.",
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
    observations = {
        "addProtection": [
            {"action": "wrap ceramic mug", "visibleObjects": ["ceramic mug", "bubble wrap"]}
        ]
    }
    citations = {
        "addProtection": {
            "documentId": "doc-01",
            "page": 4,
            "section": "Cushioning",
            "excerpt": "Two complete layers required."
        }
    }

    res = bedrockCaller.composeSkillContent("s1", observations, citations)
    assert res.title == "Pack fragile item"

    # Verify prompt body contains observation facts and policy citations
    callBody = json.loads(mockClient.invoke_model.call_args[1]["body"])
    userPrompt = callBody["messages"][0]["content"]
    assert "wrap ceramic mug" in userPrompt
    assert "Two complete layers required" in userPrompt

def testAudioSynthesisWritesRealBytesAndMatchesReportedSize() -> None:
    mockStorage = MagicMock()
    writtenFiles = {}
    mockStorage.writeAsset.side_effect = lambda k, b: writtenFiles.update({k: b}) or k

    mockPolly = MagicMock()
    fakeAudio = b"ID3\x04\x00\x00\x00\x00\x00#\xff\xfb\x90d" + b"polly-synthetic-bytes-test"
    mockPolly.synthesize_speech.return_value = {"AudioStream": io.BytesIO(fakeAudio)}

    pollyService = AmazonPollyService(pollyClient=mockPolly)
    approvedSkill = {
        "skillId": "skill-test-01",
        "status": "approved",
        "version": 1,
        "approvedBy": "supervisor-jane",
        "steps": [
            {"stepId": "step-001", "instruction": "Inspect product", "instructionHi": "उत्पाद जांचें"}
        ]
    }

    descriptors = pollyService.synthesizeApprovedSkillAudio(approvedSkill, language="hiIN", storageAdapter=mockStorage)
    desc = descriptors["step-001"]

    assert desc.sizeBytes == len(fakeAudio)
    assert desc.storageKey in writtenFiles
    assert writtenFiles[desc.storageKey] == fakeAudio

def testApprovedOnlyTranslation() -> None:
    bundlePath = getFixturePath("evidenceBundle.valid.json")
    with open(bundlePath, "r", encoding="utf-8") as f:
        bundle = json.load(f)

    adapter = MockSkillEngineAdapter()
    draft = adapter.composeDraft(bundle)

    translator = LocalTranslationService()

    with pytest.raises(ValueError, match="Draft skills cannot be translated"):
        translator.translateApprovedSkill(draft)

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
