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
from skillEngine.policyExtractor import PdfPolicyExtractor, PolicyDocument, PolicyIndex, PolicySection
from skillEngine.policyVerifier import PolicyVerifier
from skillEngine.production import ProductionSkillEngine, buildProductionEngine
from skillEngine.publication import PublicationService
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
    assert "untrusted source data" in userPrompt


def testBedrockCompositionFailsClosedWithoutExplicitFallback() -> None:
    mockClient = MagicMock()
    mockClient.invoke_model.side_effect = RuntimeError("provider unavailable")
    caller = BedrockModelCaller(bedrockClient=mockClient)

    with pytest.raises(RuntimeError, match="failed closed"):
        caller.composeSkillContent("skill-1", {}, {})


def testStrictBedrockGroundingRejectsInventedMaterial() -> None:
    modelJson = {
        "title": "Pack item",
        "materials": ["diamond foam"],
        "prerequisites": [],
        "instructions": {
            action: "Supervisor review is required."
            for action in ["selectProduct", "selectBox", "addProtection", "placeProduct", "sealBox", "attachLabel"]
        },
    }
    mockClient = MagicMock()
    mockClient.invoke_model.return_value = {
        "body": io.BytesIO(json.dumps({
            "content": [{"type": "text", "text": json.dumps(modelJson)}]
        }).encode("utf-8"))
    }
    caller = BedrockModelCaller(bedrockClient=mockClient, strictGrounding=True)

    with pytest.raises(RuntimeError, match="Ungrounded material"):
        caller.composeSkillContent("skill-1", {}, {})


def testPolicyIndexRanksMultipleExactCandidates() -> None:
    index = PolicyIndex()
    index.indexDocument(PolicyDocument("policy-a", [
        PolicySection("policy-a", 1, "General", "Keep the station clean."),
        PolicySection("policy-a", 2, "CUSHIONING", "Fragile items require two complete layers of bubble wrap."),
        PolicySection("policy-a", 3, "Materials", "Bubble wrap may be recycled when undamaged."),
    ]))

    candidates = index.findCitations("addProtection", limit=2)

    assert len(candidates) == 2
    assert candidates[0]["page"] == 2
    assert candidates[0]["excerpt"] == "Fragile items require two complete layers of bubble wrap."


def testAsyncTextractPollingAndPagination() -> None:
    mockClient = MagicMock()
    mockClient.start_document_text_detection.return_value = {"JobId": "textract-job-1"}
    mockClient.get_document_text_detection.side_effect = [
        {"JobStatus": "IN_PROGRESS"},
        {
            "JobStatus": "SUCCEEDED",
            "Blocks": [
                {"BlockType": "PAGE", "Page": 1},
                {"BlockType": "LINE", "Page": 1, "Text": "INSPECTION"},
            ],
            "NextToken": "page-2",
        },
        {
            "JobStatus": "SUCCEEDED",
            "Blocks": [
                {"BlockType": "PAGE", "Page": 2},
                {"BlockType": "LINE", "Page": 2, "Text": "Two complete layers required."},
            ],
        },
    ]
    extractor = TextractPolicyExtractor(textractClient=mockClient)

    document = extractor.extractS3Document(
        "policy-scan",
        "private-bucket",
        "skills/s1/policies/scan.pdf",
        maxPolls=3,
        pollIntervalSeconds=0,
        sleep=lambda _: None,
    )

    assert [section.page for section in document.sections] == [1, 2]
    assert document.sections[1].text == "Two complete layers required."
    mockClient.start_document_text_detection.assert_called_once()


def testProductionCompositionLoadsAndPersistsGroundedDraft() -> None:
    bundle = json.loads(getFixturePath("evidenceBundle.valid.json").read_text(encoding="utf-8"))
    assets = {
        "skills/s1/evidence.json": json.dumps(bundle).encode("utf-8"),
        "skills/s1/policies/policy.pdf": getAssetPath("samplePolicy.pdf").read_bytes(),
    }

    class MemoryStorage:
        def readAsset(self, key: str) -> bytes:
            return assets[key]

        def writeAsset(self, key: str, data: bytes) -> str:
            assets[key] = data
            return key

    engine = ProductionSkillEngine(
        storage=MemoryStorage(),
        bucket="private-bucket",
        modelCaller=LocalModelCaller(),
    )
    result = engine.composeFromStorage(
        "skills/s1/evidence.json",
        ["skills/s1/policies/policy.pdf"],
    )

    draft = result["skillPackage"]
    assert draft["status"] == "reviewRequired"
    assert draft["version"] == 0
    assert len(draft["steps"]) == 6
    assert result["skillPackageKey"] in assets
    assert json.loads(assets[result["skillPackageKey"]])["skillId"] == bundle["skillId"]


def testProductionConfigurationIsRequired() -> None:
    with pytest.raises(RuntimeError, match="AWS_REGION.*SKILLTWIN_BUCKET.*SKILL_ENGINE_MODEL_ID"):
        buildProductionEngine({})

def testAudioSynthesisWritesRealBytesAndMatchesReportedSize() -> None:
    mockStorage = MagicMock()
    writtenFiles = {}
    mockStorage.writeAsset.side_effect = lambda k, b: writtenFiles.update({k: b}) or k
    mockStorage.readAsset.side_effect = lambda k: writtenFiles[k]

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


def testAmazonTranslateRejectsEmptyOutput() -> None:
    mockClient = MagicMock()
    mockClient.translate_text.return_value = {"TranslatedText": ""}
    translator = AmazonTranslateService(translateClient=mockClient)
    approvedSkill = {
        "status": "approved",
        "version": 1,
        "approvedBy": "supervisor-jane",
        "steps": [{"stepId": "step-001", "instruction": "Inspect product"}],
    }

    with pytest.raises(RuntimeError, match="empty result"):
        translator.translateApprovedSkill(approvedSkill)


def testAmazonTranslatePreservesConfiguredTechnicalTerms() -> None:
    mockClient = MagicMock()
    mockClient.translate_text.return_value = {"TranslatedText": "बॉक्स को सील करें"}
    translator = AmazonTranslateService(
        translateClient=mockClient,
        fixedTerms=["H tape"],
    )
    approvedSkill = {
        "status": "approved",
        "version": 1,
        "approvedBy": "supervisor-jane",
        "steps": [{"stepId": "step-001", "instruction": "Seal with H tape"}],
    }

    with pytest.raises(RuntimeError, match="H tape"):
        translator.translateApprovedSkill(approvedSkill)


def testPollyRejectsEmptyAudioInsteadOfFabricatingBytes() -> None:
    mockPolly = MagicMock()
    mockPolly.synthesize_speech.return_value = {"AudioStream": io.BytesIO(b"")}
    storage = MagicMock()
    storage.writeAsset.side_effect = lambda key, data: key
    storage.readAsset.return_value = b""
    service = AmazonPollyService(pollyClient=mockPolly)
    approvedSkill = {
        "skillId": "skill-1",
        "status": "approved",
        "version": 1,
        "approvedBy": "supervisor-jane",
        "steps": [{"stepId": "step-001", "instructionHi": "उत्पाद जांचें"}],
    }

    with pytest.raises(RuntimeError, match="invalid MP3"):
        service.synthesizeApprovedSkillAudio(approvedSkill, storageAdapter=storage)


def testPollyStrictlyRejectsDraftSkill() -> None:
    service = AmazonPollyService(pollyClient=MagicMock())
    with pytest.raises(ValueError, match="Draft skills cannot synthesize audio"):
        service.synthesizeApprovedSkillAudio(
            {"status": "reviewRequired", "version": 0, "approvedBy": None, "steps": []},
            storageAdapter=MagicMock(),
        )


def testPublicationIsIdempotentAndPreservesApprovedSnapshot() -> None:
    approvedSkill = json.loads(
        getFixturePath("skillPackage.approved.valid.json").read_text(encoding="utf-8")
    )
    original = json.loads(json.dumps(approvedSkill))

    class MemoryStorage:
        def __init__(self) -> None:
            self.assets = {"skills/s1/sop/v1.pdf": b"%PDF-verified"}

        def readAsset(self, key: str) -> bytes:
            return self.assets[key]

        def writeAsset(self, key: str, data: bytes) -> str:
            self.assets[key] = data
            return key

        def assetExists(self, key: str) -> bool:
            return key in self.assets

    storage = MemoryStorage()
    translateClient = MagicMock()
    translateClient.translate_text.side_effect = lambda **request: {
        "TranslatedText": f"{request['Text']} हिंदी"
    }
    pollyClient = MagicMock()
    pollyClient.synthesize_speech.side_effect = lambda **_: {
        "AudioStream": io.BytesIO(b"ID3\x04\x00\x00\x00\x00\x00#published-audio")
    }
    service = PublicationService(
        translator=AmazonTranslateService(
            translateClient=translateClient,
            fixedTerms=[],
        ),
        audioService=AmazonPollyService(pollyClient=pollyClient),
        storage=storage,
    )

    first = service.publishApprovedSkill(approvedSkill, ["skills/s1/sop/v1.pdf"])
    second = service.publishApprovedSkill(approvedSkill, ["skills/s1/sop/v1.pdf"])

    assert first == second
    assert approvedSkill == original
    assert first["approvedContentHash"] == PublicationService.approvedContentHash(original)
    assert len(first["translationKeys"]) == 6
    assert len(first["audioArtifacts"]) == 6
    assert translateClient.translate_text.call_count == 6
    assert pollyClient.synthesize_speech.call_count == 6
    published = json.loads(storage.assets[first["publishedSkillKey"]])
    assert published["status"] == "published"
    assert all(step["instructionHi"] and step["audioKey"] for step in published["steps"])

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
