import io
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from mediaIntelligence.audioDetector import AudioDetector
from mediaIntelligence.bedrockObserver import BedrockObserver
from mediaIntelligence.bundleComposer import BundleComposer
from mediaIntelligence.mockAdapter import MockMediaIntelligenceAdapter
from mediaIntelligence.observer import LocalMediaObserver, Observation
from mediaIntelligence.pipeline import processAssetManifest
from mediaIntelligence.storage import LocalStorageAdapter, S3StorageAdapter
from mediaIntelligence.transcriber import AmazonTranscribeService, LocalTranscribeService
from mediaIntelligence.validator import validateSchema
from mediaIntelligence.videoValidator import VideoMetadata, VideoValidator

def getFixturePath(filename: str) -> Path:
    repoRoot = Path(__file__).resolve().parent.parent.parent.parent
    return repoRoot / "packages" / "contracts" / "fixtures" / filename

def getAssetPath(filename: str) -> Path:
    return Path(__file__).resolve().parent / "assets" / filename

def testMockAdapterBaseline() -> None:
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

def testProcessRealSilentVideo() -> None:
    assetDir = getAssetPath("")
    manifest = {
        "schemaVersion": 1,
        "skillId": "skill-silent-001",
        "workflowType": "fragilePackingV1",
        "title": "Silent packing test",
        "videos": [
            {
                "videoId": "video-silent-001",
                "sourceKey": "silent_pack.mp4",
                "mimeType": "video/mp4"
            }
        ],
        "referenceImages": [],
        "documents": [],
        "sourceLanguage": "enIN",
        "outputLanguages": ["enIN"],
        "expectedObjects": ["ceramic mug"],
        "supervisorNotes": None
    }

    bundle = processAssetManifest(manifest, assetRoot=assetDir)

    assert bundle["schemaVersion"] == 1
    assert bundle["skillId"] == "skill-silent-001"
    assert len(bundle["videos"]) == 1

    videoRecord = bundle["videos"][0]
    assert videoRecord["videoId"] == "video-silent-001"
    assert videoRecord["hasNarration"] is False
    assert videoRecord["transcriptKey"] is None

    assert len(bundle["observations"]) > 0
    for obs in bundle["observations"]:
        assert obs["videoId"] == "video-silent-001"
        assert obs["spokenEvidence"] is None
        assert obs["endMs"] > obs["startMs"]
        assert 0.0 <= obs["confidence"] <= 1.0

    valid, error = validateSchema("evidenceBundle", bundle)
    assert valid, f"Schema error: {error}"

def testProcessRealNarratedVideo() -> None:
    assetDir = getAssetPath("")
    manifest = {
        "schemaVersion": 1,
        "skillId": "skill-narrated-001",
        "workflowType": "fragilePackingV1",
        "title": "Narrated packing test",
        "videos": [
            {
                "videoId": "video-narrated-001",
                "sourceKey": "narrated_pack.mp4",
                "mimeType": "video/mp4"
            }
        ],
        "referenceImages": [
            {
                "imageId": "img-001",
                "sourceKey": "reference_mug.jpg",
                "mimeType": "image/jpeg"
            }
        ],
        "documents": [],
        "sourceLanguage": "enIN",
        "outputLanguages": ["enIN"],
        "expectedObjects": ["ceramic mug"],
        "supervisorNotes": "Audio narration included"
    }

    bundle = processAssetManifest(manifest, assetRoot=assetDir)

    assert bundle["schemaVersion"] == 1
    assert len(bundle["videos"]) == 1

    vRecord = bundle["videos"][0]
    assert vRecord["videoId"] == "video-narrated-001"
    assert vRecord["hasNarration"] is True
    assert vRecord["transcriptKey"] is not None

    storage = LocalStorageAdapter(assetDir)
    assert storage.assetExists(vRecord["transcriptKey"])

    hasSpokenEvidence = any(obs["spokenEvidence"] is not None for obs in bundle["observations"])
    assert hasSpokenEvidence is True

    valid, error = validateSchema("evidenceBundle", bundle)
    assert valid, f"Schema error: {error}"

def testProcessToneNoSpeechVideo() -> None:
    assetDir = getAssetPath("")
    manifest = {
        "schemaVersion": 1,
        "skillId": "skill-tone-001",
        "workflowType": "fragilePackingV1",
        "title": "Tone audio packing test",
        "videos": [
            {
                "videoId": "video-tone-001",
                "sourceKey": "tone_no_speech.mp4",
                "mimeType": "video/mp4"
            }
        ],
        "referenceImages": [],
        "documents": [],
        "sourceLanguage": "enIN",
        "outputLanguages": ["enIN"],
        "expectedObjects": ["cardboard box"],
        "supervisorNotes": None
    }

    bundle = processAssetManifest(manifest, assetRoot=assetDir)

    vRecord = bundle["videos"][0]
    assert vRecord["hasNarration"] is False
    assert vRecord["transcriptKey"] is None

    for obs in bundle["observations"]:
        assert obs["spokenEvidence"] is None

    valid, error = validateSchema("evidenceBundle", bundle)
    assert valid, f"Schema error: {error}"

def testProcessTwoVideosIndependently() -> None:
    assetDir = getAssetPath("")
    manifestPath = assetDir / "testManifestReal.json"
    with open(manifestPath, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    bundle = processAssetManifest(manifest, assetRoot=assetDir)

    assert len(bundle["videos"]) == 2
    assert bundle["videos"][0]["videoId"] == "video-001"
    assert bundle["videos"][1]["videoId"] == "video-002"

    obsIds = [obs["observationId"] for obs in bundle["observations"]]
    assert len(obsIds) == len(set(obsIds))
    assert obsIds[0] == "obs-001"
    assert obsIds[1] == "obs-002"

    v1Observations = [o for o in bundle["observations"] if o["videoId"] == "video-001"]
    v2Observations = [o for o in bundle["observations"] if o["videoId"] == "video-002"]
    assert len(v1Observations) > 0
    assert len(v2Observations) > 0

    assert v1Observations[0]["startMs"] == 0
    assert v2Observations[0]["startMs"] == 0

    valid, error = validateSchema("evidenceBundle", bundle)
    assert valid, f"Schema error: {error}"

def testInvalidManifestRejection() -> None:
    manifestPath = getFixturePath("assetManifest.unknownField.invalid.json")
    with open(manifestPath, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    with pytest.raises(ValueError):
        processAssetManifest(manifest, assetRoot=getAssetPath(""))

def testUnsupportedMediaTypeRejection() -> None:
    manifest = {
        "schemaVersion": 1,
        "skillId": "skill-unsupported-001",
        "workflowType": "fragilePackingV1",
        "title": "Unsupported media",
        "videos": [
            {
                "videoId": "video-unsupported-001",
                "sourceKey": "silent_pack.mp4",
                "mimeType": "text/plain"
            }
        ],
        "referenceImages": [],
        "documents": [],
        "sourceLanguage": "enIN",
        "outputLanguages": ["enIN"],
        "expectedObjects": ["ceramic mug"],
        "supervisorNotes": None
    }

    with pytest.raises(ValueError, match="Unsupported media type"):
        processAssetManifest(manifest, assetRoot=getAssetPath(""))

def testCorruptVideoRejection() -> None:
    manifest = {
        "schemaVersion": 1,
        "skillId": "skill-corrupt-001",
        "workflowType": "fragilePackingV1",
        "title": "Corrupt video test",
        "videos": [
            {
                "videoId": "video-corrupt-001",
                "sourceKey": "corrupt_video.mp4",
                "mimeType": "video/mp4"
            }
        ],
        "referenceImages": [],
        "documents": [],
        "sourceLanguage": "enIN",
        "outputLanguages": ["enIN"],
        "expectedObjects": ["ceramic mug"],
        "supervisorNotes": None
    }

    with pytest.raises(ValueError, match="empty or corrupted|cannot be opened"):
        processAssetManifest(manifest, assetRoot=getAssetPath(""))

def testExcessiveDurationRejection() -> None:
    validator = VideoValidator()
    mockPath = getAssetPath("silent_pack.mp4")

    vRecord = {
        "videoId": "video-long-001",
        "sourceKey": "silent_pack.mp4",
        "mimeType": "video/mp4"
    }

    origMax = validator.MAX_DURATION_MS
    try:
        validator.MAX_DURATION_MS = 500
        with pytest.raises(ValueError, match="exceeds maximum release limit"):
            validator.validateVideoRecord(vRecord, mockPath)
    finally:
        validator.MAX_DURATION_MS = origMax

def testLocalStorageSafeTraversal() -> None:
    storage = LocalStorageAdapter(getAssetPath(""))
    key = "test_write.txt"
    storage.writeAsset(key, b"hello storage")
    assert storage.assetExists(key)
    assert storage.readAsset(key) == b"hello storage"

    with pytest.raises(ValueError, match="traversal"):
        storage.readAsset("../../../windows/system32/cmd.exe")

def testS3StorageAdapterMock() -> None:
    mockS3 = MagicMock()
    mockS3.get_object.return_value = {"Body": io.BytesIO(b"s3 binary data")}
    mockS3.head_object.return_value = {}

    adapter = S3StorageAdapter("test-bucket", s3Client=mockS3)
    data = adapter.readAsset("skills/skill-001/video.mp4")
    assert data == b"s3 binary data"

    resKey = adapter.writeAsset("skills/skill-001/frame.jpg", b"frame data")
    assert resKey == "skills/skill-001/frame.jpg"
    mockS3.put_object.assert_called_once()

    assert adapter.assetExists("skills/skill-001/video.mp4") is True

def testBedrockObserverMockSuccess() -> None:
    mockBedrock = MagicMock()
    modelOutput = {
        "content": [
            {
                "type": "text",
                "text": json.dumps([
                    {
                        "startMs": 0,
                        "endMs": 1500,
                        "beforeState": "shelf with mugs",
                        "action": "inspect ceramic mug",
                        "afterState": "mug on table",
                        "visibleObjects": ["ceramic mug"],
                        "spokenEvidence": "Inspect mug first",
                        "candidateAction": "selectProduct",
                        "referenceFrameKey": "skills/skill-001/derived/frames/v1/0.jpg",
                        "confidence": 0.96
                    }
                ])
            }
        ]
    }
    mockBedrock.invoke_model.return_value = {
        "body": io.BytesIO(json.dumps(modelOutput).encode("utf-8"))
    }

    observer = BedrockObserver(bedrockClient=mockBedrock)
    from mediaIntelligence.videoSampler import SampledFrame
    frames = [
        SampledFrame("v1", 0, 0, "skills/skill-001/derived/frames/v1/0.jpg", b"fakejpg", 160, 120)
    ]
    observations = observer.observeVideo("v1", "skill-001", frames, [])

    assert len(observations) == 1
    assert observations[0].candidateAction == "selectProduct"
    assert observations[0].confidence == 0.96

def testBedrockObserverMalformedFallback() -> None:
    mockBedrock = MagicMock()
    badOutput = {
        "content": [
            {
                "type": "text",
                "text": "This is unformatted plain text"
            }
        ]
    }
    mockBedrock.invoke_model.return_value = {
        "body": io.BytesIO(json.dumps(badOutput).encode("utf-8"))
    }

    localFallback = LocalMediaObserver()
    observer = BedrockObserver(bedrockClient=mockBedrock, fallbackObserver=localFallback)

    from mediaIntelligence.videoSampler import SampledFrame
    frames = [
        SampledFrame("v1", 0, 0, "skills/skill-001/derived/frames/v1/0.jpg", b"fakejpg", 160, 120),
        SampledFrame("v1", 1500, 15, "skills/skill-001/derived/frames/v1/1500.jpg", b"fakejpg2", 160, 120)
    ]
    observations = observer.observeVideo("v1", "skill-001", frames, [])

    assert len(observations) == 2
    assert observations[0].candidateAction == "selectProduct"

def testAmazonTranscribeServiceMock() -> None:
    mockTranscribe = MagicMock()
    mockTranscribe.start_transcription_job.return_value = {
        "TranscriptionJob": {
            "TranscriptionJobStatus": "IN_PROGRESS"
        }
    }

    service = AmazonTranscribeService(transcribeClient=mockTranscribe)
    storage = LocalStorageAdapter(getAssetPath(""))

    transcriptKey = service.transcribeVideo(
        videoId="video-001",
        skillId="skill-001",
        localFilePath=None,
        storageAdapter=storage
    )

    assert transcriptKey == "skills/skill-001/derived/transcripts/video-001.json"
    mockTranscribe.start_transcription_job.assert_called_once()

def testMissingFrameRejectionInBundleComposer() -> None:
    composer = BundleComposer()
    storage = LocalStorageAdapter(getAssetPath(""))

    videoRecords = [{"videoId": "v1", "hasNarration": False, "transcriptKey": None}]
    obs = Observation(
        observationId="obs-pending",
        videoId="v1",
        startMs=0,
        endMs=1000,
        beforeState="init",
        action="act",
        afterState="done",
        visibleObjects=["item"],
        spokenEvidence=None,
        candidateAction="selectProduct",
        referenceFrameKey="nonexistent/frame/key.jpg",
        confidence=0.9
    )

    with pytest.raises(ValueError, match="Reference frame does not exist"):
        composer.composeBundle("skill-001", videoRecords, {"v1": [obs]}, storage)
