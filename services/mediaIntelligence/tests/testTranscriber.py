import io
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mediaIntelligence.errors import (
    TranscriptParseError,
    TranscriptionAccessDeniedError,
    TranscriptionFailedError,
    TranscriptionPendingError,
    TranscriptionTimeoutError,
    TranscriptionTransientError,
)
from mediaIntelligence.storage import LocalStorageAdapter
from mediaIntelligence.transcriber import (
    AmazonTranscribeService,
    TranscriptionState,
    TranscriptionStatus,
)


class ProviderError(Exception):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}


def service(transcribe: MagicMock, s3: MagicMock | None = None) -> AmazonTranscribeService:
    return AmazonTranscribeService(
        sourceBucket="source-bucket",
        outputBucket="output-bucket",
        transcribeClient=transcribe,
        s3Client=s3 or MagicMock(),
    )


def transcriptDocument(language: str = "en-IN") -> bytes:
    return json.dumps({
        "results": {
            "language_codes": [{"language_code": language, "duration_in_seconds": 2.0}],
            "transcripts": [{"transcript": "Inspect ceramic mug."}],
            "items": [
                {
                    "type": "pronunciation",
                    "start_time": "0.50",
                    "end_time": "1.25",
                    "alternatives": [{"content": "Inspect", "confidence": "0.98"}],
                },
                {
                    "type": "pronunciation",
                    "start_time": "1.30",
                    "end_time": "2.00",
                    "alternatives": [{"content": "ceramic", "confidence": "0.96"}],
                },
                {
                    "type": "pronunciation",
                    "start_time": "2.05",
                    "end_time": "2.40",
                    "alternatives": [{"content": "mug", "confidence": "0.97"}],
                },
                {"type": "punctuation", "alternatives": [{"content": "."}]},
            ],
            "audio_segments": [{
                "start_time": "0.50", "end_time": "2.40",
                "transcript": "Inspect ceramic mug.",
            }],
        }
    }).encode("utf-8")


def testJobNotFoundStartsUsingRealManifestSourceKey() -> None:
    transcribe = MagicMock()
    transcribe.get_transcription_job.side_effect = ProviderError("NotFoundException")
    adapter = service(transcribe)
    status = adapter.ensureTranscriptionStarted(
        "video-1", "skill-1", "skills/skill-1/source/videos/upload-abc.mp4", "enIN", "mp4",
    )
    assert status.state == TranscriptionState.IN_PROGRESS
    request = transcribe.start_transcription_job.call_args.kwargs
    assert request["Media"]["MediaFileUri"] == (
        "s3://source-bucket/skills/skill-1/source/videos/upload-abc.mp4"
    )
    assert request["LanguageCode"] == "en-IN"
    assert "IdentifyLanguage" not in request


def testConcurrentStartConflictIsHandledIdempotently() -> None:
    transcribe = MagicMock()
    transcribe.start_transcription_job.side_effect = ProviderError("ConflictException")
    transcribe.get_transcription_job.return_value = {
        "TranscriptionJob": {"TranscriptionJobStatus": "IN_PROGRESS"}
    }
    adapter = service(transcribe)
    identity = adapter.startTranscription(
        "v", "s", "skills/s/source/videos/v.mp4", "auto", "mp4",
    )
    assert identity.jobName.startswith("skilltwin-s-v-")
    transcribe.get_transcription_job.assert_called_once_with(
        TranscriptionJobName=identity.jobName,
    )


@pytest.mark.parametrize(
    ("contractLanguage", "expected"),
    [("enIN", "en-IN"), ("hiIN", "hi-IN")],
)
def testConfiguredLanguageMapping(contractLanguage: str, expected: str) -> None:
    transcribe = MagicMock()
    adapter = service(transcribe)
    adapter.startTranscription("v", "s", "skills/s/source/videos/v.mp4", contractLanguage, "mp4")
    request = transcribe.start_transcription_job.call_args.kwargs
    assert request["LanguageCode"] == expected


def testAutoLanguageRequestsEnglishAndHindiIdentification() -> None:
    transcribe = MagicMock()
    adapter = service(transcribe)
    adapter.startTranscription("v", "s", "skills/s/source/videos/v.mp4", "auto", "mp4")
    request = transcribe.start_transcription_job.call_args.kwargs
    assert request["IdentifyLanguage"] is True
    assert request["LanguageOptions"] == ["en-IN", "hi-IN"]
    assert "LanguageCode" not in request


def testInProgressStatusRemainsPending(tmp_path: Path) -> None:
    transcribe = MagicMock()
    transcribe.get_transcription_job.return_value = {
        "TranscriptionJob": {"TranscriptionJobStatus": "IN_PROGRESS"}
    }
    adapter = service(transcribe)
    identity = adapter._identity("v", "s", "skills/s/source/videos/v.mp4", "auto")
    status = adapter.getTranscriptionStatus(identity)
    assert status.state == TranscriptionState.IN_PROGRESS
    with pytest.raises(TranscriptionPendingError):
        adapter.completeTranscription(status, LocalStorageAdapter(tmp_path))


def testCompletedAndFailedProviderStatusesRemainDistinct() -> None:
    transcribe = MagicMock()
    adapter = service(transcribe)
    identity = adapter._identity("v", "s", "skills/s/source/videos/v.mp4", "enIN")
    transcribe.get_transcription_job.return_value = {
        "TranscriptionJob": {
            "TranscriptionJobStatus": "COMPLETED",
            "LanguageCode": "en-IN",
            "Transcript": {"TranscriptFileUri": "s3://output-bucket/raw/job.json"},
        }
    }
    completed = adapter.getTranscriptionStatus(identity)
    assert completed.state == TranscriptionState.COMPLETED
    assert completed.transcriptUri == "s3://output-bucket/raw/job.json"
    assert completed.detectedLanguage == "en-IN"

    transcribe.get_transcription_job.return_value = {
        "TranscriptionJob": {
            "TranscriptionJobStatus": "FAILED",
            "FailureReason": "bad media",
        }
    }
    failed = adapter.getTranscriptionStatus(identity)
    assert failed.state == TranscriptionState.FAILED
    assert failed.failureReason == "bad media"


def testBoundedPollingTimeoutIsDistinctFromSilence() -> None:
    transcribe = MagicMock()
    transcribe.get_transcription_job.return_value = {
        "TranscriptionJob": {"TranscriptionJobStatus": "IN_PROGRESS"}
    }
    adapter = service(transcribe)
    identity = adapter._identity("v", "s", "skills/s/source/videos/v.mp4", "auto")
    clockValues = iter([0.0, 0.0, 1.0])
    with pytest.raises(TranscriptionTimeoutError):
        adapter.waitForTranscription(
            identity,
            timeoutSeconds=1.0,
            pollIntervalSeconds=1.0,
            sleepFn=lambda _seconds: None,
            monotonicFn=lambda: next(clockValues),
        )


def testCompletedTranscriptPreservesWordsTimestampsLanguageAndJob(tmp_path: Path) -> None:
    transcribe = MagicMock()
    s3 = MagicMock()
    payload = transcriptDocument("hi-IN")
    s3.get_object.return_value = {"Body": io.BytesIO(payload)}
    adapter = service(transcribe, s3)
    identity = adapter._identity("v", "s", "skills/s/source/videos/v.mp4", "auto")
    status = TranscriptionStatus(
        identity, TranscriptionState.COMPLETED,
        transcriptUri="s3://output-bucket/raw/job.json",
        detectedLanguage="hi-IN",
    )
    storage = LocalStorageAdapter(tmp_path)
    result = adapter.completeTranscription(status, storage)
    assert result.hasNarration is True
    assert result.detectedLanguage == "hi-IN"
    assert result.jobName == identity.jobName
    assert result.words[0].startMs == 500
    assert result.words[-1].endMs == 2400
    assert result.segments[0].text == "Inspect ceramic mug."
    artifact = json.loads(storage.readAsset(result.transcriptKey).decode("utf-8"))
    assert artifact["provider"]["jobName"] == identity.jobName
    assert artifact["source"]["key"] == "skills/s/source/videos/v.mp4"
    assert artifact["language"] == {"requested": "auto", "detected": "hi-IN"}
    assert artifact["words"][0]["startMs"] == 500


def testFailedTranscriptionRaisesProviderReason(tmp_path: Path) -> None:
    adapter = service(MagicMock())
    identity = adapter._identity("v", "s", "skills/s/source/videos/v.mp4", "enIN")
    status = TranscriptionStatus(
        identity, TranscriptionState.FAILED, failureReason="Unsupported media encoding",
    )
    with pytest.raises(TranscriptionFailedError, match="Unsupported media encoding"):
        adapter.completeTranscription(status, LocalStorageAdapter(tmp_path))


@pytest.mark.parametrize(
    ("code", "errorType"),
    [
        ("AccessDeniedException", TranscriptionAccessDeniedError),
        ("ThrottlingException", TranscriptionTransientError),
    ],
)
def testProviderErrorsAreNotTreatedAsNotFound(code: str, errorType: type[Exception]) -> None:
    transcribe = MagicMock()
    transcribe.get_transcription_job.side_effect = ProviderError(code)
    adapter = service(transcribe)
    identity = adapter._identity("v", "s", "skills/s/source/videos/v.mp4", "enIN")
    with pytest.raises(errorType):
        adapter.getTranscriptionStatus(identity)
    transcribe.start_transcription_job.assert_not_called()


def testMalformedCompletedTranscriptFailsClosed(tmp_path: Path) -> None:
    s3 = MagicMock()
    s3.get_object.return_value = {"Body": io.BytesIO(b"not-json")}
    adapter = service(MagicMock(), s3)
    identity = adapter._identity("v", "s", "skills/s/source/videos/v.mp4", "enIN")
    status = TranscriptionStatus(
        identity, TranscriptionState.COMPLETED,
        transcriptUri="s3://output-bucket/raw/job.json",
    )
    with pytest.raises(TranscriptParseError):
        adapter.completeTranscription(status, LocalStorageAdapter(tmp_path))


def testCompletedTranscriptCannotRedirectToAnotherBucket(tmp_path: Path) -> None:
    adapter = service(MagicMock(), MagicMock())
    identity = adapter._identity("v", "s", "skills/s/source/videos/v.mp4", "enIN")
    status = TranscriptionStatus(
        identity, TranscriptionState.COMPLETED,
        transcriptUri="s3://unexpected-bucket/raw/job.json",
    )
    with pytest.raises(TranscriptParseError, match="does not match configured output bucket"):
        adapter.completeTranscription(status, LocalStorageAdapter(tmp_path))
