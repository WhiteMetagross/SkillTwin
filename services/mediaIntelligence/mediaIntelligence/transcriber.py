from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

from .errors import (
    TranscriptParseError,
    TranscriptionAccessDeniedError,
    TranscriptionError,
    TranscriptionFailedError,
    TranscriptionJobNotFoundError,
    TranscriptionPendingError,
    TranscriptionTimeoutError,
    TranscriptionTransientError,
)
from .storage import StorageAdapter, validateStorageKey


MAX_PROVIDER_TRANSCRIPT_BYTES = 10 * 1024 * 1024
LANGUAGE_CODES = {"enIN": "en-IN", "hiIN": "hi-IN"}
TRANSIENT_CODES = {
    "ThrottlingException", "TooManyRequestsException", "LimitExceededException",
    "InternalFailureException", "InternalError", "RequestLimitExceeded",
    "ServiceUnavailable", "ServiceUnavailableException", "SlowDown", "Throttling",
}
ACCESS_CODES = {
    "AccessDenied", "AccessDeniedException", "InvalidAccessKeyId",
    "SignatureDoesNotMatch", "UnauthorizedException", "UnrecognizedClientException",
}


class TranscriptionState(str, Enum):
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class TranscriptWord:
    startMs: int
    endMs: int
    text: str
    confidence: float

    def toDict(self) -> Dict[str, Any]:
        return {
            "startMs": self.startMs,
            "endMs": self.endMs,
            "text": self.text,
            "confidence": self.confidence,
        }


@dataclass
class TranscriptSegment:
    startMs: int
    endMs: int
    text: str
    confidence: float = 0.95
    words: List[TranscriptWord] = field(default_factory=list)

    def toDict(self) -> Dict[str, Any]:
        return {
            "startMs": self.startMs,
            "endMs": self.endMs,
            "text": self.text,
            "confidence": self.confidence,
            "words": [word.toDict() for word in self.words],
        }


@dataclass(frozen=True)
class TranscriptionJobIdentity:
    provider: str
    jobName: str
    skillId: str
    videoId: str
    sourceBucket: str
    sourceKey: str
    requestedLanguage: str
    outputBucket: str

    def toDict(self) -> Dict[str, str]:
        return {
            "provider": self.provider,
            "jobName": self.jobName,
            "skillId": self.skillId,
            "videoId": self.videoId,
            "sourceBucket": self.sourceBucket,
            "sourceKey": self.sourceKey,
            "requestedLanguage": self.requestedLanguage,
            "outputBucket": self.outputBucket,
        }

    @classmethod
    def fromDict(cls, value: Dict[str, Any]) -> "TranscriptionJobIdentity":
        required = (
            "provider", "jobName", "skillId", "videoId", "sourceBucket",
            "sourceKey", "requestedLanguage", "outputBucket",
        )
        if not isinstance(value, dict) or any(not isinstance(value.get(key), str) for key in required):
            raise ValueError("Invalid serialized transcription job identity")
        return cls(**{key: value[key] for key in required})


@dataclass(frozen=True)
class TranscriptionStatus:
    identity: TranscriptionJobIdentity
    state: TranscriptionState
    transcriptUri: Optional[str] = None
    detectedLanguage: Optional[str] = None
    failureReason: Optional[str] = None

    def toDict(self) -> Dict[str, Any]:
        return {
            "job": self.identity.toDict(),
            "state": self.state.value,
            "transcriptUri": self.transcriptUri,
            "detectedLanguage": self.detectedLanguage,
            "failureReason": self.failureReason,
        }

    @classmethod
    def fromDict(cls, value: Dict[str, Any]) -> "TranscriptionStatus":
        if not isinstance(value, dict) or not isinstance(value.get("job"), dict):
            raise ValueError("Invalid serialized transcription status")
        try:
            state = TranscriptionState(value.get("state"))
        except ValueError as exc:
            raise ValueError("Invalid serialized transcription state") from exc
        return cls(
            identity=TranscriptionJobIdentity.fromDict(value["job"]),
            state=state,
            transcriptUri=value.get("transcriptUri"),
            detectedLanguage=value.get("detectedLanguage"),
            failureReason=value.get("failureReason"),
        )


@dataclass(frozen=True)
class TranscriptionResult:
    hasNarration: bool
    transcriptKey: Optional[str]
    segments: List[TranscriptSegment]
    words: List[TranscriptWord]
    requestedLanguage: str
    detectedLanguage: Optional[str]
    provider: str
    jobName: Optional[str]


def _providerErrorCode(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error", {})
        if isinstance(error, dict):
            return str(error.get("Code", ""))
    return ""


def _raiseTranscribeProviderError(exc: Exception, operation: str) -> None:
    code = _providerErrorCode(exc)
    if code in {"NotFoundException", "ResourceNotFoundException"}:
        raise TranscriptionJobNotFoundError(f"Transcription job not found during {operation}") from exc
    if code in ACCESS_CODES:
        raise TranscriptionAccessDeniedError(f"Amazon Transcribe access denied during {operation}") from exc
    if code in TRANSIENT_CODES:
        raise TranscriptionTransientError(
            f"Transient Amazon Transcribe failure during {operation}: {code}"
        ) from exc
    raise TranscriptionError(
        f"Amazon Transcribe {operation} failed: {code or type(exc).__name__}"
    ) from exc


class TranscribeService:
    def transcribe(
        self,
        videoId: str,
        skillId: str,
        localFilePath: Optional[Path],
        storageAdapter: StorageAdapter,
        sourceKey: Optional[str] = None,
        sourceLanguage: str = "auto",
    ) -> TranscriptionResult:
        raise NotImplementedError("Subclasses must implement transcribe")

    def alignTranscriptToInterval(
        self, segments: List[TranscriptSegment], startMs: int, endMs: int,
    ) -> Optional[str]:
        matching = [
            segment.text for segment in segments
            if max(startMs, segment.startMs) < min(endMs, segment.endMs)
        ]
        return " ".join(matching) if matching else None


class LocalTranscribeService(TranscribeService):
    """Explicit deterministic local/test adapter; never selected by production runtime."""

    def __init__(self, customSegmentStore: Optional[Dict[str, List[TranscriptSegment]]] = None) -> None:
        self.customSegmentStore = customSegmentStore or {}

    def transcribe(
        self,
        videoId: str,
        skillId: str,
        localFilePath: Optional[Path],
        storageAdapter: StorageAdapter,
        sourceKey: Optional[str] = None,
        sourceLanguage: str = "auto",
    ) -> TranscriptionResult:
        transcriptKey = f"skills/{skillId}/derived/transcripts/{videoId}.json"
        segments = self.customSegmentStore.get(videoId, [])
        loadedExisting = False
        if not segments and storageAdapter.assetExists(transcriptKey):
            try:
                localDocument = json.loads(storageAdapter.readAsset(transcriptKey).decode("utf-8"))
                rawSegments = localDocument.get("segments", [])
                segments = [
                    TranscriptSegment(
                        startMs=int(item["startMs"]),
                        endMs=int(item["endMs"]),
                        text=str(item["text"]),
                        confidence=float(item.get("confidence", 0.0)),
                    )
                    for item in rawSegments
                ]
                loadedExisting = True
            except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise TranscriptParseError(
                    f"Local transcript artifact is malformed: {transcriptKey}"
                ) from exc
        words = [word for segment in segments for word in segment.words]
        if not segments:
            raise TranscriptionError(
                f"Explicit local mode has no transcript fixture for narrated video '{videoId}'"
            )

        if loadedExisting:
            return TranscriptionResult(
                True, transcriptKey, segments, words, sourceLanguage, sourceLanguage,
                "local-explicit", None,
            )

        payload = {
            "schemaVersion": 1,
            "videoId": videoId,
            "status": "COMPLETED",
            "provider": {"name": "local-explicit", "jobName": None},
            "language": {"requested": sourceLanguage, "detected": sourceLanguage},
            "segments": [segment.toDict() for segment in segments],
            "words": [word.toDict() for word in words],
        }
        storageAdapter.writeAsset(transcriptKey, json.dumps(payload, indent=2).encode("utf-8"))
        return TranscriptionResult(
            True, transcriptKey, segments, words, sourceLanguage, sourceLanguage,
            "local-explicit", None,
        )


class AmazonTranscribeService(TranscribeService):
    """Step Functions-friendly Amazon Transcribe lifecycle adapter."""

    def __init__(
        self,
        sourceBucket: str,
        outputBucket: Optional[str] = None,
        transcribeClient: Optional[Any] = None,
        s3Client: Optional[Any] = None,
    ) -> None:
        if not sourceBucket:
            raise ValueError("Amazon Transcribe source bucket is required")
        self.sourceBucket = sourceBucket
        self.outputBucket = outputBucket or sourceBucket
        self.transcribeClient = transcribeClient
        self.s3Client = s3Client

    def _getTranscribeClient(self) -> Any:
        if self.transcribeClient is not None:
            return self.transcribeClient
        import boto3
        return boto3.client("transcribe")

    def _getS3Client(self) -> Any:
        if self.s3Client is not None:
            return self.s3Client
        import boto3
        return boto3.client("s3")

    def _identity(
        self, videoId: str, skillId: str, sourceKey: str, sourceLanguage: str,
    ) -> TranscriptionJobIdentity:
        if not re.fullmatch(r"[0-9A-Za-z._-]+", skillId):
            raise ValueError(f"Invalid skillId for transcription: {skillId}")
        if not re.fullmatch(r"[0-9A-Za-z._-]+", videoId):
            raise ValueError(f"Invalid videoId for transcription: {videoId}")
        validateStorageKey(sourceKey)
        if sourceLanguage not in {"auto", "enIN", "hiIN"}:
            raise ValueError(f"Unsupported SkillTwin source language: {sourceLanguage}")
        safeSkill = re.sub(r"[^0-9A-Za-z._-]", "-", skillId)[:60]
        safeVideo = re.sub(r"[^0-9A-Za-z._-]", "-", videoId)[:60]
        digest = hashlib.sha256(sourceKey.encode("utf-8")).hexdigest()[:12]
        jobName = f"skilltwin-{safeSkill}-{safeVideo}-{digest}"[:200]
        return TranscriptionJobIdentity(
            provider="amazon-transcribe",
            jobName=jobName,
            skillId=skillId,
            videoId=videoId,
            sourceBucket=self.sourceBucket,
            sourceKey=sourceKey,
            requestedLanguage=sourceLanguage,
            outputBucket=self.outputBucket,
        )

    def startTranscription(
        self,
        videoId: str,
        skillId: str,
        sourceKey: str,
        sourceLanguage: str,
        mediaFormat: str,
    ) -> TranscriptionJobIdentity:
        if mediaFormat not in {"mp4", "webm"}:
            raise ValueError(f"Unsupported Amazon Transcribe media format: {mediaFormat}")
        identity = self._identity(videoId, skillId, sourceKey, sourceLanguage)
        outputKey = f"skills/{skillId}/derived/transcribe/{videoId}/{identity.jobName}.json"
        request: Dict[str, Any] = {
            "TranscriptionJobName": identity.jobName,
            "MediaFormat": mediaFormat,
            "Media": {"MediaFileUri": f"s3://{self.sourceBucket}/{sourceKey}"},
            "OutputBucketName": self.outputBucket,
            "OutputKey": outputKey,
        }
        if sourceLanguage == "auto":
            request["IdentifyLanguage"] = True
            request["LanguageOptions"] = ["en-IN", "hi-IN"]
        else:
            request["LanguageCode"] = LANGUAGE_CODES[sourceLanguage]
        try:
            self._getTranscribeClient().start_transcription_job(**request)
        except Exception as exc:
            if _providerErrorCode(exc) == "ConflictException":
                # A concurrent retry may have created the same deterministic job.
                self.getTranscriptionStatus(identity)
                return identity
            _raiseTranscribeProviderError(exc, "start_transcription_job")
        return identity

    def getTranscriptionStatus(
        self, identity: TranscriptionJobIdentity,
    ) -> TranscriptionStatus:
        try:
            response = self._getTranscribeClient().get_transcription_job(
                TranscriptionJobName=identity.jobName
            )
        except Exception as exc:
            _raiseTranscribeProviderError(exc, "get_transcription_job")
        job = response.get("TranscriptionJob")
        if not isinstance(job, dict):
            raise TranscriptionError("Amazon Transcribe returned no TranscriptionJob object")
        rawState = job.get("TranscriptionJobStatus")
        try:
            state = TranscriptionState(rawState)
        except ValueError as exc:
            raise TranscriptionError(f"Unknown Amazon Transcribe job status: {rawState}") from exc
        transcript = job.get("Transcript", {})
        transcriptUri = transcript.get("TranscriptFileUri") if isinstance(transcript, dict) else None
        return TranscriptionStatus(
            identity=identity,
            state=state,
            transcriptUri=transcriptUri,
            detectedLanguage=job.get("LanguageCode"),
            failureReason=job.get("FailureReason"),
        )

    def ensureTranscriptionStarted(
        self,
        videoId: str,
        skillId: str,
        sourceKey: str,
        sourceLanguage: str,
        mediaFormat: str,
    ) -> TranscriptionStatus:
        identity = self._identity(videoId, skillId, sourceKey, sourceLanguage)
        try:
            return self.getTranscriptionStatus(identity)
        except TranscriptionJobNotFoundError:
            started = self.startTranscription(
                videoId, skillId, sourceKey, sourceLanguage, mediaFormat,
            )
            return TranscriptionStatus(started, TranscriptionState.IN_PROGRESS)

    def waitForTranscription(
        self,
        identity: TranscriptionJobIdentity,
        timeoutSeconds: float = 300.0,
        pollIntervalSeconds: float = 2.0,
        sleepFn: Any = time.sleep,
        monotonicFn: Any = time.monotonic,
    ) -> TranscriptionStatus:
        if timeoutSeconds <= 0 or pollIntervalSeconds <= 0:
            raise ValueError("Polling timeout and interval must be positive")
        deadline = monotonicFn() + timeoutSeconds
        while True:
            status = self.getTranscriptionStatus(identity)
            if status.state in {TranscriptionState.COMPLETED, TranscriptionState.FAILED}:
                return status
            remaining = deadline - monotonicFn()
            if remaining <= 0:
                raise TranscriptionTimeoutError(
                    f"Transcription job {identity.jobName} did not finish within {timeoutSeconds} seconds"
                )
            sleepFn(min(pollIntervalSeconds, remaining))

    def completeTranscription(
        self,
        status: TranscriptionStatus,
        storageAdapter: StorageAdapter,
    ) -> TranscriptionResult:
        if status.state in {TranscriptionState.QUEUED, TranscriptionState.IN_PROGRESS}:
            raise TranscriptionPendingError(
                f"Transcription job {status.identity.jobName} is {status.state.value}"
            )
        if status.state == TranscriptionState.FAILED:
            raise TranscriptionFailedError(
                f"Transcription job {status.identity.jobName} failed: "
                f"{status.failureReason or 'provider supplied no reason'}"
            )
        if not status.transcriptUri:
            raise TranscriptParseError("Completed transcription has no TranscriptFileUri")

        document = self._readProviderTranscript(status.transcriptUri)
        segments, words, transcriptText = self._parseTranscriptDocument(document)
        detectedLanguage = status.detectedLanguage or self._extractDetectedLanguage(document)
        if not segments or not transcriptText.strip():
            return TranscriptionResult(
                False, None, [], words, status.identity.requestedLanguage,
                detectedLanguage, status.identity.provider, status.identity.jobName,
            )

        transcriptKey = (
            f"skills/{status.identity.skillId}/derived/transcripts/"
            f"{status.identity.videoId}.json"
        )
        payload = {
            "schemaVersion": 1,
            "videoId": status.identity.videoId,
            "status": "COMPLETED",
            "provider": {
                "name": status.identity.provider,
                "jobName": status.identity.jobName,
            },
            "source": {
                "bucket": status.identity.sourceBucket,
                "key": status.identity.sourceKey,
            },
            "language": {
                "requested": status.identity.requestedLanguage,
                "detected": detectedLanguage,
            },
            "transcript": transcriptText,
            "segments": [segment.toDict() for segment in segments],
            "words": [word.toDict() for word in words],
        }
        storageAdapter.writeAsset(transcriptKey, json.dumps(payload, indent=2).encode("utf-8"))
        if not storageAdapter.assetExists(transcriptKey):
            raise TranscriptionError(f"Transcript artifact was not persisted: {transcriptKey}")
        return TranscriptionResult(
            True, transcriptKey, segments, words, status.identity.requestedLanguage,
            detectedLanguage, status.identity.provider, status.identity.jobName,
        )

    def transcribe(
        self,
        videoId: str,
        skillId: str,
        localFilePath: Optional[Path],
        storageAdapter: StorageAdapter,
        sourceKey: Optional[str] = None,
        sourceLanguage: str = "auto",
    ) -> TranscriptionResult:
        if not sourceKey:
            raise ValueError("Amazon Transcribe requires the manifest sourceKey")
        mediaFormat = self._mediaFormat(sourceKey)
        status = self.ensureTranscriptionStarted(
            videoId, skillId, sourceKey, sourceLanguage, mediaFormat,
        )
        if status.state in {TranscriptionState.QUEUED, TranscriptionState.IN_PROGRESS}:
            raise TranscriptionPendingError(
                f"Transcription job {status.identity.jobName} is {status.state.value}"
            )
        return self.completeTranscription(status, storageAdapter)

    @staticmethod
    def _mediaFormat(sourceKey: str) -> str:
        extension = Path(sourceKey).suffix.lower().lstrip(".")
        mapping = {"mp4": "mp4", "webm": "webm", "mov": "mp4"}
        if extension not in mapping:
            raise ValueError(f"Unsupported transcription media extension: {extension}")
        return mapping[extension]

    def _readProviderTranscript(self, transcriptUri: str) -> Dict[str, Any]:
        bucket, key = self._parseTranscriptLocation(transcriptUri)
        try:
            response = self._getS3Client().get_object(Bucket=bucket, Key=key)
            body = response.get("Body")
            if body is None or not hasattr(body, "read"):
                raise TranscriptParseError("Transcript S3 response has no readable body")
            chunks: List[bytes] = []
            total = 0
            try:
                while True:
                    chunk = body.read(64 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_PROVIDER_TRANSCRIPT_BYTES:
                        raise TranscriptParseError("Provider transcript exceeds 10 MiB limit")
                    chunks.append(chunk)
            finally:
                close = getattr(body, "close", None)
                if callable(close):
                    close()
        except TranscriptParseError:
            raise
        except Exception as exc:
            _raiseTranscribeProviderError(exc, "read transcript object")
        try:
            document = json.loads(b"".join(chunks).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TranscriptParseError("Provider transcript is not valid UTF-8 JSON") from exc
        if not isinstance(document, dict) or not isinstance(document.get("results"), dict):
            raise TranscriptParseError("Provider transcript is missing results")
        return document

    def _parseTranscriptLocation(self, transcriptUri: str) -> tuple[str, str]:
        parsed = urlparse(transcriptUri)
        if parsed.scheme == "s3":
            bucket = parsed.netloc
            key = unquote(parsed.path.lstrip("/"))
        elif parsed.scheme in {"http", "https"}:
            host = parsed.netloc.split(":", 1)[0]
            key = unquote(parsed.path.lstrip("/"))
            if ".s3" in host:
                bucket = host.split(".s3", 1)[0]
            else:
                bucket = self.outputBucket
                if key.startswith(bucket + "/"):
                    key = key[len(bucket) + 1 :]
        else:
            raise TranscriptParseError(f"Unsupported TranscriptFileUri scheme: {parsed.scheme}")
        if not bucket or not key:
            raise TranscriptParseError("TranscriptFileUri does not identify an S3 bucket and key")
        if bucket != self.outputBucket:
            raise TranscriptParseError(
                f"TranscriptFileUri bucket '{bucket}' does not match configured output bucket"
            )
        return bucket, key

    @staticmethod
    def _parseTranscriptDocument(
        document: Dict[str, Any],
    ) -> tuple[List[TranscriptSegment], List[TranscriptWord], str]:
        results = document["results"]
        rawItems = results.get("items", [])
        if not isinstance(rawItems, list):
            raise TranscriptParseError("Transcript results.items must be an array")
        words: List[TranscriptWord] = []
        pendingPunctuation: List[str] = []
        for item in rawItems:
            if not isinstance(item, dict):
                raise TranscriptParseError("Transcript item must be an object")
            alternatives = item.get("alternatives", [])
            if not alternatives or not isinstance(alternatives[0], dict):
                raise TranscriptParseError("Transcript item has no alternative")
            content = str(alternatives[0].get("content", "")).strip()
            if item.get("type") == "punctuation":
                if content:
                    pendingPunctuation.append(content)
                continue
            if item.get("type") != "pronunciation":
                raise TranscriptParseError(f"Unsupported transcript item type: {item.get('type')}")
            try:
                startMs = round(float(item["start_time"]) * 1000)
                endMs = round(float(item["end_time"]) * 1000)
                confidence = float(alternatives[0].get("confidence", 0.0))
            except (KeyError, TypeError, ValueError) as exc:
                raise TranscriptParseError("Pronunciation item has invalid timing or confidence") from exc
            if not content or startMs < 0 or endMs <= startMs or not 0.0 <= confidence <= 1.0:
                raise TranscriptParseError("Pronunciation item violates transcript bounds")
            if pendingPunctuation and words:
                previous = words[-1]
                words[-1] = TranscriptWord(
                    previous.startMs, previous.endMs,
                    previous.text + "".join(pendingPunctuation), previous.confidence,
                )
                pendingPunctuation.clear()
            words.append(TranscriptWord(startMs, endMs, content, confidence))
        if pendingPunctuation and words:
            previous = words[-1]
            words[-1] = TranscriptWord(
                previous.startMs, previous.endMs,
                previous.text + "".join(pendingPunctuation), previous.confidence,
            )

        rawSegments = results.get("audio_segments", [])
        segments: List[TranscriptSegment] = []
        if isinstance(rawSegments, list) and rawSegments:
            for rawSegment in rawSegments:
                try:
                    startMs = round(float(rawSegment["start_time"]) * 1000)
                    endMs = round(float(rawSegment["end_time"]) * 1000)
                    text = str(rawSegment["transcript"]).strip()
                except (KeyError, TypeError, ValueError) as exc:
                    raise TranscriptParseError("Audio segment has invalid fields") from exc
                segmentWords = [w for w in words if max(startMs, w.startMs) < min(endMs, w.endMs)]
                confidence = (
                    sum(word.confidence for word in segmentWords) / len(segmentWords)
                    if segmentWords else 0.0
                )
                if text and endMs > startMs:
                    segments.append(TranscriptSegment(startMs, endMs, text, confidence, segmentWords))
        else:
            segments = [
                TranscriptSegment(word.startMs, word.endMs, word.text, word.confidence, [word])
                for word in words
            ]

        transcripts = results.get("transcripts", [])
        transcriptText = ""
        if isinstance(transcripts, list) and transcripts and isinstance(transcripts[0], dict):
            transcriptText = str(transcripts[0].get("transcript", "")).strip()
        if not transcriptText:
            transcriptText = " ".join(word.text for word in words)
        return segments, words, transcriptText

    @staticmethod
    def _extractDetectedLanguage(document: Dict[str, Any]) -> Optional[str]:
        results = document.get("results", {})
        codes = results.get("language_codes", []) if isinstance(results, dict) else []
        if isinstance(codes, list) and codes and isinstance(codes[0], dict):
            code = codes[0].get("language_code")
            return str(code) if code else None
        return None
