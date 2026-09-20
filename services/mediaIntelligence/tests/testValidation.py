from pathlib import Path
import shutil
from unittest.mock import MagicMock

import pytest

from mediaIntelligence.audioDetector import AudioInspectionResult
from mediaIntelligence.errors import TranscriptionPendingError
from mediaIntelligence.pipeline import processAssetManifest
from mediaIntelligence.storage import LocalStorageAdapter, validateOwnedSourceKey
from mediaIntelligence.videoValidator import VideoValidator
from mediaIntelligence.videoSampler import VideoSampler


ASSETS = Path(__file__).resolve().parent / "assets"


class SpeechDetector:
    def inspectAudio(self, _path: Path) -> AudioInspectionResult:
        return AudioInspectionResult(True, True, inspectedDurationMs=2000)


def videoRecord(mimeType: str = "video/mp4") -> dict:
    return {"videoId": "v1", "sourceKey": "video.mp4", "mimeType": mimeType}


def manifest(mimeType: str = "video/mp4") -> dict:
    return {
        "schemaVersion": 1,
        "skillId": "s1",
        "workflowType": "fragilePackingV1",
        "title": "Validation test",
        "videos": [videoRecord(mimeType)],
        "referenceImages": [],
        "documents": [],
        "sourceLanguage": "auto",
        "outputLanguages": ["enIN"],
        "expectedObjects": [],
        "supervisorNotes": None,
    }


def testCorruptMediaRejectedBeforeAudioOrObserver(tmp_path: Path) -> None:
    shutil.copy2(ASSETS / "corrupt_video.mp4", tmp_path / "video.mp4")
    observer = MagicMock()
    transcriber = MagicMock()
    with pytest.raises(ValueError, match="empty or corrupted|opened or decoded"):
        processAssetManifest(
            manifest(), assetRoot=tmp_path, observer=observer, transcriber=transcriber,
        )
    observer.observeVideo.assert_not_called()
    transcriber.transcribe.assert_not_called()


def testUnsupportedMimeRejectedBeforeProviderCalls(tmp_path: Path) -> None:
    shutil.copy2(ASSETS / "silent_pack.mp4", tmp_path / "video.mp4")
    observer = MagicMock()
    with pytest.raises(ValueError, match="Unsupported media type"):
        processAssetManifest(manifest("application/octet-stream"), assetRoot=tmp_path, observer=observer)
    observer.observeVideo.assert_not_called()


def testVideoExtensionMustMatchDeclaredMime(tmp_path: Path) -> None:
    target = tmp_path / "video.webm"
    shutil.copy2(ASSETS / "silent_pack.mp4", target)
    record = {"videoId": "v1", "sourceKey": "video.webm", "mimeType": "video/mp4"}
    with pytest.raises(ValueError, match="extension"):
        VideoValidator().validateVideoRecord(record, target)


def testOversizeLocalVideoRejectedWithoutReadingIntoMemory(tmp_path: Path) -> None:
    target = tmp_path / "video.mp4"
    with target.open("wb") as output:
        output.truncate(VideoValidator.MAX_FILE_BYTES + 1)
    with pytest.raises(ValueError, match="exceeds limit"):
        VideoValidator().validateVideoRecord(videoRecord(), target)


def testDurationOver180SecondsRejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "video.mp4"
    target.write_bytes(b"0" * 100)
    capture = MagicMock()
    capture.isOpened.return_value = True
    capture.read.return_value = (True, MagicMock())
    values = {
        5: 30.0,  # CAP_PROP_FPS
        7: 5401,  # CAP_PROP_FRAME_COUNT
        3: 1280,  # CAP_PROP_FRAME_WIDTH
        4: 720,   # CAP_PROP_FRAME_HEIGHT
    }
    capture.get.side_effect = lambda prop: values.get(prop, 0)
    monkeypatch.setattr(
        "mediaIntelligence.videoValidator.cv2.VideoCapture", lambda _path: capture,
    )
    with pytest.raises(ValueError, match="exceeds maximum release limit"):
        VideoValidator().validateVideoRecord(videoRecord(), target)


def testFrameSamplerRejectsUnboundedFrameRequest() -> None:
    with pytest.raises(ValueError, match="maxFrames"):
        VideoSampler(maxFrames=VideoSampler.MAX_FRAMES + 1)


def testOwnedManifestKeysRejectCrossSkillAndWrongAssetType() -> None:
    with pytest.raises(ValueError, match="not owned"):
        validateOwnedSourceKey("s1", "skills/s2/source/videos/v.mp4", "videos")
    with pytest.raises(ValueError, match="not owned"):
        validateOwnedSourceKey("s1", "skills/s1/source/images/v.mp4", "videos")
    assert validateOwnedSourceKey(
        "s1", "skills/s1/source/videos/v.mp4", "videos",
    ).endswith("v.mp4")


def testPendingTranscriptionPropagatesAndIsNeverMarkedSilent(tmp_path: Path) -> None:
    shutil.copy2(ASSETS / "narrated_pack.mp4", tmp_path / "video.mp4")
    transcriber = MagicMock()
    transcriber.transcribe.side_effect = TranscriptionPendingError("job is IN_PROGRESS")
    observer = MagicMock()
    with pytest.raises(TranscriptionPendingError, match="IN_PROGRESS"):
        processAssetManifest(
            manifest(),
            assetRoot=tmp_path,
            audioDetector=SpeechDetector(),
            transcriber=transcriber,
            observer=observer,
        )
    observer.observeVideo.assert_not_called()
    assert not (tmp_path / "skills" / "s1" / "derived" / "transcripts" / "v1.json").exists()


def testStrictManifestOwnershipAppliesBeforeProcessing(tmp_path: Path) -> None:
    shutil.copy2(ASSETS / "silent_pack.mp4", tmp_path / "video.mp4")
    with pytest.raises(ValueError, match="not owned"):
        processAssetManifest(
            manifest(),
            storageAdapter=LocalStorageAdapter(tmp_path),
            enforceOwnedKeys=True,
        )
