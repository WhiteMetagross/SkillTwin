import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch
from PIL import Image
import pytest
from mediaIntelligence.audioDetector import AudioDetector
from mediaIntelligence.bedrockObserver import BedrockObserver
from mediaIntelligence.bundleComposer import BundleComposer
from mediaIntelligence.cli import main as cliMain
from mediaIntelligence.mockAdapter import MockMediaIntelligenceAdapter
from mediaIntelligence.observer import (
    DeterministicMockObserver,
    LocalMediaObserver,
    Observation
)
from mediaIntelligence.pipeline import processAssetManifest
from mediaIntelligence.production import ProductionConfig, buildProductionRuntime
from mediaIntelligence.storage import LocalStorageAdapter, S3StorageAdapter
from mediaIntelligence.transcriber import (
    AmazonTranscribeService,
    LocalTranscribeService,
    TranscriptionPendingError,
    TranscriptionProviderError,
    TranscriptionState
)
from mediaIntelligence.validator import validateSchema
from mediaIntelligence.videoSampler import SampledFrame, VideoSampler
from mediaIntelligence.videoValidator import VideoMetadata, VideoValidator

def getFixturePath(filename: str) -> Path:
    repoRoot = Path(__file__).resolve().parent.parent.parent.parent
    return repoRoot / "packages" / "contracts" / "fixtures" / filename

def getAssetPath(filename: str) -> Path:
    return Path(__file__).resolve().parent / "assets" / filename

def createTempAssetRoot(tmp_path: Path, *filenames: str) -> Path:
    for filename in filenames:
        shutil.copy2(getAssetPath(filename), tmp_path / filename)
    return tmp_path

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

def testCliRequiresExplicitRuntimeMode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["skilltwin-media-intelligence", "--manifest", "manifest.json"]
    )
    with pytest.raises(SystemExit) as exc:
        cliMain()
    assert exc.value.code == 2

def testProductionConfigFailsWhenRequiredProviderSettingsAreMissing(tmp_path: Path) -> None:
    ffmpeg = tmp_path / "ffmpeg"
    ffprobe = tmp_path / "ffprobe"
    ffmpeg.touch()
    ffprobe.touch()
    environment = {
        "AWS_REGION": "ap-south-1",
        "S3_MEDIA_BUCKET": "media-bucket",
        "TRANSCRIBE_OUTPUT_BUCKET": "transcript-bucket",
        "FFMPEG_PATH": str(ffmpeg),
        "FFPROBE_PATH": str(ffprobe)
    }

    with pytest.raises(RuntimeError, match="BEDROCK_OBSERVER_MODEL_ID"):
        ProductionConfig.fromEnvironment(environment)

def testProductionRuntimeUsesOnlyScopedAwsAdapters(tmp_path: Path) -> None:
    ffmpeg = tmp_path / "ffmpeg"
    ffprobe = tmp_path / "ffprobe"
    ffmpeg.touch()
    ffprobe.touch()
    config = ProductionConfig.fromEnvironment({
        "AWS_REGION": "ap-south-1",
        "S3_MEDIA_BUCKET": "media-bucket",
        "TRANSCRIBE_OUTPUT_BUCKET": "transcript-bucket",
        "BEDROCK_OBSERVER_MODEL_ID": "test-model",
        "FFMPEG_PATH": str(ffmpeg),
        "FFPROBE_PATH": str(ffprobe)
    })

    class FakeSession:
        def __init__(self, region_name: str) -> None:
            self.regionName = region_name
            self.clients = {}

        def client(self, serviceName: str) -> MagicMock:
            client = MagicMock(name=serviceName)
            self.clients[serviceName] = client
            return client

    sessions = []

    def sessionFactory(**kwargs):
        session = FakeSession(kwargs["region_name"])
        sessions.append(session)
        return session

    runtime = buildProductionRuntime("skill-001", config, sessionFactory=sessionFactory)

    assert sessions[0].regionName == "ap-south-1"
    assert runtime.storage.bucketName == "media-bucket"
    assert runtime.storage.allowedPrefix == "skills/skill-001/"
    assert runtime.transcriber.outputBucket == "transcript-bucket"
    assert runtime.observer.modelId == "test-model"
    assert set(sessions[0].clients) == {"s3", "transcribe", "bedrock-runtime"}

def testProcessRealSilentVideo(tmp_path: Path) -> None:
    assetDir = createTempAssetRoot(tmp_path, "silent_pack.mp4")
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

def testProcessRealNarratedVideo(tmp_path: Path) -> None:
    assetDir = createTempAssetRoot(tmp_path, "narrated_pack.mp4", "reference_mug.jpg")
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

def testProcessToneNoSpeechVideo(tmp_path: Path) -> None:
    assetDir = createTempAssetRoot(tmp_path, "tone_no_speech.mp4")
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

def testProcessTwoVideosIndependently(tmp_path: Path) -> None:
    assetDir = createTempAssetRoot(
        tmp_path,
        "narrated_pack.mp4",
        "silent_pack.mp4",
        "reference_mug.jpg"
    )
    manifestPath = getAssetPath("testManifestReal.json")
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

def testIdenticalNarratedBytesUnderDifferentFilenames() -> None:
    detector = AudioDetector()
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

def testCompletedTranscriptArtifactAndPendingJobRejection(tmp_path: Path) -> None:
    mockTranscribe = MagicMock()
    # Case 1: Job is IN_PROGRESS -> must not return a transcript key
    mockTranscribe.get_transcription_job.return_value = {
        "TranscriptionJob": {
            "TranscriptionJobStatus": "IN_PROGRESS"
        }
    }

    service = AmazonTranscribeService(transcribeClient=mockTranscribe)
    storage = LocalStorageAdapter(tmp_path)

    with pytest.raises(TranscriptionPendingError) as pending:
        service.transcribe("v1", "skill-001", None, storage)
    assert pending.value.state == TranscriptionState.IN_PROGRESS

    # Case 2: Job is COMPLETED -> parses segments and writes artifact
    transcriptJsonContent = json.dumps({
        "results": {
            "items": [
                {
                    "type": "pronunciation",
                    "start_time": "0.5",
                    "end_time": "2.0",
                    "alternatives": [{"content": "Inspect ceramic mug", "confidence": "0.98"}]
                }
            ]
        }
    })

    mockTranscribe.get_transcription_job.return_value = {
        "TranscriptionJob": {
            "TranscriptionJobStatus": "COMPLETED",
            "LanguageCode": "en-IN",
            "Transcript": {
                "TranscriptFileUri": transcriptJsonContent
            }
        }
    }

    compKey, compSegs = service.transcribe("v1", "skill-001", None, storage)
    assert compKey is not None
    assert len(compSegs) == 1
    assert compSegs[0].text == "Inspect ceramic mug"
    assert compSegs[0].startMs == 500
    assert compSegs[0].languageCode == "en-IN"
    assert storage.assetExists(compKey) is True

def testTranscribeStartsMissingJobWithExactSourceKeyAndLanguage(tmp_path: Path) -> None:
    class ProviderException(Exception):
        def __init__(self) -> None:
            self.response = {
                "Error": {
                    "Code": "ResourceNotFoundException",
                    "Message": "job not found"
                }
            }

    mockTranscribe = MagicMock()
    mockTranscribe.get_transcription_job.side_effect = ProviderException()
    mockTranscribe.start_transcription_job.return_value = {
        "TranscriptionJob": {"TranscriptionJobStatus": "QUEUED"}
    }
    service = AmazonTranscribeService(
        transcribeClient=mockTranscribe,
        sourceBucket="media-bucket",
        outputBucket="output-bucket"
    )

    with pytest.raises(TranscriptionPendingError) as pending:
        service.transcribe(
            "video-001",
            "skill-001",
            None,
            LocalStorageAdapter(tmp_path),
            sourceKey="skills/skill-001/source/assets/asset-123",
            sourceLanguage="hiIN"
        )

    assert pending.value.state == TranscriptionState.QUEUED
    request = mockTranscribe.start_transcription_job.call_args.kwargs
    assert request["Media"]["MediaFileUri"] == (
        "s3://media-bucket/skills/skill-001/source/assets/asset-123"
    )
    assert request["LanguageCode"] == "hi-IN"
    assert "IdentifyLanguage" not in request

def testTranscribeDifferentiatesAccessDeniedFromMissingJob(tmp_path: Path) -> None:
    class ProviderException(Exception):
        def __init__(self) -> None:
            self.response = {
                "Error": {
                    "Code": "AccessDeniedException",
                    "Message": "not authorized"
                }
            }

    mockTranscribe = MagicMock()
    mockTranscribe.get_transcription_job.side_effect = ProviderException()
    service = AmazonTranscribeService(transcribeClient=mockTranscribe)

    with pytest.raises(TranscriptionProviderError) as denied:
        service.transcribe("video-001", "skill-001", None, LocalStorageAdapter(tmp_path))

    assert denied.value.code == "accessDenied"
    mockTranscribe.start_transcription_job.assert_not_called()

def testTranscribeAutoLanguageRequestAndFailedState(tmp_path: Path) -> None:
    mockTranscribe = MagicMock()
    mockTranscribe.start_transcription_job.return_value = {
        "TranscriptionJob": {"TranscriptionJobStatus": "IN_PROGRESS"}
    }
    service = AmazonTranscribeService(
        transcribeClient=mockTranscribe,
        sourceBucket="media-bucket"
    )
    started = service.startTranscription(
        "video-001",
        "skill-001",
        "skills/skill-001/source/video.mp4",
        "auto"
    )
    request = mockTranscribe.start_transcription_job.call_args.kwargs
    assert started.state == TranscriptionState.IN_PROGRESS
    assert request["IdentifyLanguage"] is True
    assert request["LanguageOptions"] == ["en-IN", "hi-IN"]

    mockTranscribe.get_transcription_job.return_value = {
        "TranscriptionJob": {
            "TranscriptionJobStatus": "FAILED",
            "FailureReason": "Unsupported media"
        }
    }
    with pytest.raises(TranscriptionProviderError) as failed:
        service.transcribe(
            "video-001",
            "skill-001",
            None,
            LocalStorageAdapter(tmp_path)
        )
    assert failed.value.code == "failed"
    assert "Unsupported media" in str(failed.value)

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

def testS3InputStagesLocallyForValidationAndSampling() -> None:
    mockS3 = MagicMock()
    realVideoBytes = getAssetPath("silent_pack.mp4").read_bytes()

    mockS3.head_object.return_value = {"ContentLength": len(realVideoBytes)}
    mockS3.get_object.return_value = {"Body": io.BytesIO(realVideoBytes)}

    adapter = S3StorageAdapter("test-bucket", s3Client=mockS3)
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

def testS3StagingRemovesPartialFileOnDownloadFailure(tmp_path: Path) -> None:
    class FailingBody:
        def __init__(self) -> None:
            self.readCount = 0
            self.closed = False

        def read(self, _size: int) -> bytes:
            self.readCount += 1
            if self.readCount == 1:
                return b"partial"
            raise OSError("simulated interrupted download")

        def close(self) -> None:
            self.closed = True

    body = FailingBody()
    mockS3 = MagicMock()
    mockS3.head_object.return_value = {"ContentLength": 100}
    mockS3.get_object.return_value = {"Body": body}
    adapter = S3StorageAdapter("test-bucket", s3Client=mockS3, stagingRoot=tmp_path)

    with pytest.raises(OSError, match="interrupted download"):
        adapter.resolveLocalPath("skills/s1/source/videos/video.mp4")

    assert list(tmp_path.iterdir()) == []
    assert body.closed is True

def testS3StagingRejectsLengthMismatchAndWrongOwnerPrefix(tmp_path: Path) -> None:
    mockS3 = MagicMock()
    mockS3.head_object.return_value = {"ContentLength": 4}
    mockS3.get_object.return_value = {"Body": io.BytesIO(b"five!")}
    adapter = S3StorageAdapter(
        "test-bucket",
        s3Client=mockS3,
        allowedPrefix="skills/s1",
        stagingRoot=tmp_path
    )

    with pytest.raises(ValueError, match="downloaded 5 bytes, expected 4"):
        adapter.resolveLocalPath("skills/s1/source/videos/video.mp4")
    assert list(tmp_path.iterdir()) == []

    with pytest.raises(ValueError, match="outside allowed prefix"):
        adapter.resolveLocalPath("skills/s2/source/videos/video.mp4")

def testS3ReadAssetIsBounded() -> None:
    mockS3 = MagicMock()
    mockS3.get_object.return_value = {"Body": io.BytesIO(b"12345")}
    adapter = S3StorageAdapter("test-bucket", s3Client=mockS3)
    adapter.MAX_REMOTE_BYTES = 4

    with pytest.raises(ValueError, match="byte limit"):
        adapter.readAsset("skills/s1/derived/transcripts/video.json")

def testAudioInspectionCoversCompleteValidatedClip() -> None:
    pcm = b"\x01\x00" * 3200
    with patch("mediaIntelligence.audioDetector.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout=pcm, stderr=b"")
        detector = AudioDetector(ffmpegPath="ffmpeg")
        detector._analyzeAcousticSpeech(Path("video.mp4"))

    command = run.call_args.args[0]
    assert "-t" not in command

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
    observations = observer.observeVideo("v1", "skill-001", frames, [])
    # Must fail closed with empty list, never returning canned observations
    assert observations == []
