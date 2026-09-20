import io
import json
from pathlib import Path
import shutil
import tempfile
from unittest.mock import MagicMock
from PIL import Image
import pytest
from mediaIntelligence.audioDetector import AudioDetector, AudioInspectionResult
from mediaIntelligence.bedrockObserver import BedrockObserver
from mediaIntelligence.bundleComposer import BundleComposer
from mediaIntelligence.errors import ObservationProviderError
from mediaIntelligence.mockAdapter import MockMediaIntelligenceAdapter
from mediaIntelligence.observer import (
    LocalMediaObserver,
    Observation
)
from mediaIntelligence.pipeline import processAssetManifest
from mediaIntelligence.storage import LocalStorageAdapter, S3StorageAdapter
from mediaIntelligence.transcriber import LocalTranscribeService, TranscriptSegment
from mediaIntelligence.validator import validateSchema
from mediaIntelligence.videoSampler import SampledFrame
from mediaIntelligence.videoValidator import VideoValidator

def getFixturePath(filename: str) -> Path:
    repoRoot = Path(__file__).resolve().parent.parent.parent.parent
    return repoRoot / "packages" / "contracts" / "fixtures" / filename

def getAssetPath(filename: str) -> Path:
    return Path(__file__).resolve().parent / "assets" / filename

@pytest.fixture
def assetRoot(tmp_path: Path) -> Path:
    for filename in ("silent_pack.mp4", "narrated_pack.mp4", "tone_no_speech.mp4", "reference_mug.jpg"):
        shutil.copy2(getAssetPath(filename), tmp_path / filename)
    return tmp_path

class FixedAudioDetector:
    def __init__(self, speechByName: dict[str, bool]) -> None:
        self.speechByName = speechByName

    def inspectAudio(self, localFilePath: Path) -> AudioInspectionResult:
        speech = self.speechByName.get(localFilePath.name, False)
        return AudioInspectionResult(True, speech, inspectedDurationMs=2000)

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

def testProcessRealSilentVideo(assetRoot: Path) -> None:
    assetDir = assetRoot
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

    bundle = processAssetManifest(
        manifest,
        assetRoot=assetDir,
        audioDetector=FixedAudioDetector({"silent_pack.mp4": False}),
    )

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

def testProcessRealNarratedVideo(assetRoot: Path) -> None:
    assetDir = assetRoot
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

    transcript = TranscriptSegment(500, 2000, "Inspect the ceramic mug", 0.98)
    bundle = processAssetManifest(
        manifest,
        assetRoot=assetDir,
        audioDetector=FixedAudioDetector({"narrated_pack.mp4": True}),
        transcriber=LocalTranscribeService({"video-narrated-001": [transcript]}),
    )

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

def testProcessToneNoSpeechVideo(assetRoot: Path) -> None:
    assetDir = assetRoot
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

    bundle = processAssetManifest(
        manifest,
        assetRoot=assetDir,
        audioDetector=FixedAudioDetector({"tone_no_speech.mp4": False}),
    )

    vRecord = bundle["videos"][0]
    assert vRecord["hasNarration"] is False
    assert vRecord["transcriptKey"] is None

    for obs in bundle["observations"]:
        assert obs["spokenEvidence"] is None

    valid, error = validateSchema("evidenceBundle", bundle)
    assert valid, f"Schema error: {error}"

def testProcessTwoVideosIndependently(assetRoot: Path) -> None:
    assetDir = assetRoot
    manifestPath = getAssetPath("testManifestReal.json")
    with open(manifestPath, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    manifest["documents"] = []
    transcript = TranscriptSegment(500, 2000, "Inspect the ceramic mug", 0.98)
    bundle = processAssetManifest(
        manifest,
        assetRoot=assetDir,
        audioDetector=FixedAudioDetector({"narrated_pack.mp4": True, "silent_pack.mp4": False}),
        transcriber=LocalTranscribeService({"video-001": [transcript]}),
    )

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

def testIdenticalNarratedBytesUnderDifferentFilenames() -> None:
    detector = AudioDetector()
    if not detector.ffmpegPath or not detector.ffprobePath:
        pytest.skip("ffmpeg and ffprobe are exercised by the container smoke/test environment")
    narratedOriginal = getAssetPath("narrated_pack.mp4")
    originalResult = detector.inspectAudio(narratedOriginal)
    assert originalResult.hasUsableSpeech is True

    # Create temporary copy with an arbitrary non descriptive filename
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tempPath = Path(tmp.name)

    try:
        tempPath.write_bytes(narratedOriginal.read_bytes())
        renamedResult = detector.inspectAudio(tempPath)
        assert renamedResult.hasAudioTrack is True
        assert renamedResult.hasUsableSpeech is True
    finally:
        if tempPath.is_file():
            tempPath.unlink()

def testCompletedTranscriptArtifactUsesTemporaryStorage(tmp_path: Path) -> None:
    storage = LocalStorageAdapter(tmp_path)
    service = LocalTranscribeService({
        "v1": [TranscriptSegment(500, 2000, "Inspect ceramic mug", 0.98)]
    })
    result = service.transcribe("v1", "skill-001", None, storage, sourceLanguage="enIN")
    assert result.transcriptKey is not None
    assert result.hasNarration is True
    assert result.segments[0].startMs == 500
    assert storage.assetExists(result.transcriptKey) is True

def testBlankOrIrrelevantFramesProduceNoCannedObservations() -> None:
    observer = LocalMediaObserver()

    # Generate solid gray blank frames
    blankBuf = io.BytesIO()
    Image.new("RGB", (160, 120), (120, 120, 120)).save(blankBuf, format="JPEG")
    blankBytes = blankBuf.getvalue()

    frames = [
        SampledFrame("v-blank", 0, 0, "skills/s1/frames/0.jpg", blankBytes, 160, 120),
        SampledFrame("v-blank", 1500, 15, "skills/s1/frames/1500.jpg", blankBytes, 160, 120)
    ]

    observations = observer.observeVideo("v-blank", "s1", frames, [])
    # Real observer must fail closed rather than emitting canned mug/box observations
    assert len(observations) == 0

def testLocalStorageCannotReadOutsideAssetRoot() -> None:
    assetDir = getAssetPath("")
    storage = LocalStorageAdapter(assetDir)

    # Attempt to read README.md from working directory which is outside assetDir
    with pytest.raises(FileNotFoundError):
        storage.readAsset("README.md")

    # Attempt directory traversal
    with pytest.raises(ValueError, match="traversal"):
        storage.readAsset("../../../package.json")

def testS3InputStagesLocallyForValidationAndSampling(tmp_path: Path) -> None:
    mockS3 = MagicMock()
    realVideoBytes = getAssetPath("silent_pack.mp4").read_bytes()

    mockS3.head_object.return_value = {"ContentLength": len(realVideoBytes)}
    mockS3.get_object.return_value = {"Body": io.BytesIO(realVideoBytes)}

    adapter = S3StorageAdapter("test-bucket", s3Client=mockS3, stagingDirectory=tmp_path)
    stagedPath = adapter.resolveLocalPath("skills/s1/source/videos/video-001.mp4")

    assert stagedPath is not None
    assert stagedPath.is_file()
    assert stagedPath.stat().st_size == len(realVideoBytes)

    # Verify validator can decode the staged file
    validator = VideoValidator()
    meta = validator.validateVideoRecord(
        {"videoId": "video-001", "sourceKey": "skills/s1/source/videos/video-001.mp4", "mimeType": "video/mp4"},
        stagedPath
    )
    assert meta.durationMs > 0

    # Cleanup removes the staged file
    adapter.cleanup()
    assert not stagedPath.is_file()

def testObserverIntervalExceedingVideoDurationRejection() -> None:
    composer = BundleComposer()
    storage = LocalStorageAdapter(getAssetPath(""))
    frameKey = "skills/skill-fragile-mug-001/derived/frames/video-001/0.jpg"

    videoRecords = [{"videoId": "v1", "hasNarration": False, "transcriptKey": None}]
    obs = Observation(
        observationId="obs-pending",
        videoId="v1",
        startMs=0,
        endMs=5000,
        beforeState="init",
        action="act",
        afterState="done",
        visibleObjects=["item"],
        spokenEvidence=None,
        candidateAction="selectProduct",
        referenceFrameKey=frameKey,
        confidence=0.9
    )

    # Video duration is 2500ms, but observation endMs is 5000ms
    with pytest.raises(ValueError, match="exceeds video duration"):
        composer.composeBundle(
            skillId="s1",
            videoRecords=videoRecords,
            perVideoObservations={"v1": [obs]},
            storageAdapter=storage,
            videoDurationMap={"v1": 2500}
        )

def testUnsuppliedReferenceFrameKeyRejection() -> None:
    composer = BundleComposer()
    storage = LocalStorageAdapter(getAssetPath(""))
    frameKey = "skills/skill-fragile-mug-001/derived/frames/video-001/0.jpg"

    videoRecords = [{"videoId": "v1", "hasNarration": False, "transcriptKey": None}]
    obs = Observation(
        observationId="obs-pending",
        videoId="v1",
        startMs=0,
        endMs=1500,
        beforeState="init",
        action="act",
        afterState="done",
        visibleObjects=["item"],
        spokenEvidence=None,
        candidateAction="selectProduct",
        referenceFrameKey=frameKey,
        confidence=0.9
    )

    # Supplied keys set does not include frameKey
    with pytest.raises(ValueError, match="was not in supplied sampled frames"):
        composer.composeBundle(
            skillId="s1",
            videoRecords=videoRecords,
            perVideoObservations={"v1": [obs]},
            storageAdapter=storage,
            suppliedFrameKeysMap={"v1": {"skills/different/frame.jpg"}}
        )

def testBedrockObserverFailsClosedOnError() -> None:
    mockBedrock = MagicMock()
    mockBedrock.invoke_model.side_effect = RuntimeError("Bedrock runtime error")

    observer = BedrockObserver(bedrockClient=mockBedrock)
    frames = [
        SampledFrame("v1", 0, 0, "skills/skill-001/derived/frames/v1/0.jpg", b"fakejpg", 160, 120)
    ]
    with pytest.raises(ObservationProviderError, match="Bedrock observation failed"):
        observer.observeVideo("v1", "skill-001", frames, [])
