import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from .storage import StorageAdapter


class TranscriptSegment:
    def __init__(
        self,
        startMs: int,
        endMs: int,
        text: str,
        confidence: float = 0.95,
        languageCode: Optional[str] = None
    ) -> None:
        self.startMs = startMs
        self.endMs = endMs
        self.text = text
        self.confidence = confidence
        self.languageCode = languageCode

    def toDict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "startMs": self.startMs,
            "endMs": self.endMs,
            "text": self.text,
            "confidence": self.confidence
        }
        if self.languageCode:
            result["languageCode"] = self.languageCode
        return result


class TranscriptionState(str, Enum):
    NOT_FOUND = "notFound"
    QUEUED = "queued"
    IN_PROGRESS = "inProgress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class TranscriptionJobStatus:
    jobName: str
    state: TranscriptionState
    transcriptUri: Optional[str] = None
    languageCode: Optional[str] = None
    failureReason: Optional[str] = None


class TranscriptionProviderError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class TranscriptionPendingError(RuntimeError):
    def __init__(self, jobName: str, state: TranscriptionState) -> None:
        super().__init__(f"Transcription job {jobName} is {state.value}")
        self.jobName = jobName
        self.state = state


class TranscribeService:
    def transcribe(
        self,
        videoId: str,
        skillId: str,
        localFilePath: Optional[Path],
        storageAdapter: StorageAdapter,
        sourceKey: Optional[str] = None,
        sourceLanguage: str = "auto"
    ) -> Tuple[Optional[str], List[TranscriptSegment]]:
        raise NotImplementedError("Subclasses must implement transcribe")

    def alignTranscriptToInterval(
        self,
        segments: List[TranscriptSegment],
        startMs: int,
        endMs: int
    ) -> Optional[str]:
        matching = []
        for segment in segments:
            if max(startMs, segment.startMs) < min(endMs, segment.endMs):
                matching.append(segment.text)
        return " ".join(matching) if matching else None


class LocalTranscribeService(TranscribeService):
    """Explicit local-demo transcriber used only by tests and local mode."""

    def __init__(self, customSegmentStore: Optional[Dict[str, List[TranscriptSegment]]] = None) -> None:
        self.customSegmentStore = customSegmentStore or {}

    def transcribe(
        self,
        videoId: str,
        skillId: str,
        localFilePath: Optional[Path],
        storageAdapter: StorageAdapter,
        sourceKey: Optional[str] = None,
        sourceLanguage: str = "auto"
    ) -> Tuple[Optional[str], List[TranscriptSegment]]:
        del sourceKey, sourceLanguage
        segments: List[TranscriptSegment] = []

        if videoId in self.customSegmentStore:
            segments = self.customSegmentStore[videoId]
        elif localFilePath and localFilePath.is_file():
            from .audioDetector import AudioDetector
            inspection = AudioDetector().inspectAudio(localFilePath)
            if inspection.hasUsableSpeech:
                segments = [
                    TranscriptSegment(500, 1500, "Inspect the ceramic mug for cracks first", 0.96),
                    TranscriptSegment(1500, 2500, "Choose the small standard box", 0.94)
                ]

        if not segments:
            return None, []

        transcriptKey = f"skills/{skillId}/derived/transcripts/{videoId}.json"
        payload = {
            "schemaVersion": 1,
            "videoId": videoId,
            "segments": [segment.toDict() for segment in segments]
        }
        storageAdapter.writeAsset(transcriptKey, json.dumps(payload, indent=2).encode("utf-8"))
        return transcriptKey, segments


class AmazonTranscribeService(TranscribeService):
    """Asynchronous Amazon Transcribe adapter suitable for Step Functions polling."""

    LANGUAGE_CODES = {
        "enIN": "en-IN",
        "hiIN": "hi-IN"
    }

    def __init__(
        self,
        transcribeClient: Optional[Any] = None,
        s3Client: Optional[Any] = None,
        sourceBucket: str = "skilltwin-media",
        outputBucket: str = "skilltwin-media",
        mediaFormat: str = "mp4",
        regionName: Optional[str] = None
    ) -> None:
        self.transcribeClient = transcribeClient
        self.s3Client = s3Client
        self.sourceBucket = sourceBucket
        self.outputBucket = outputBucket
        self.mediaFormat = mediaFormat
        self.regionName = regionName

    def _getTranscribeClient(self) -> Any:
        if self.transcribeClient is not None:
            return self.transcribeClient
        import boto3
        return boto3.client("transcribe", region_name=self.regionName)

    def _getS3Client(self) -> Any:
        if self.s3Client is not None:
            return self.s3Client
        import boto3
        return boto3.client("s3", region_name=self.regionName)

    def buildJobName(self, skillId: str, videoId: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9._-]", "-", f"skilltwin-{skillId}-{videoId}")
        return safe[:200]

    def startTranscription(
        self,
        videoId: str,
        skillId: str,
        sourceKey: str,
        sourceLanguage: str
    ) -> TranscriptionJobStatus:
        if not sourceKey:
            raise ValueError("A server-issued sourceKey is required for Amazon Transcribe")
        jobName = self.buildJobName(skillId, videoId)
        request: Dict[str, Any] = {
            "TranscriptionJobName": jobName,
            "MediaFormat": self.mediaFormat,
            "Media": {"MediaFileUri": f"s3://{self.sourceBucket}/{sourceKey}"},
            "OutputBucketName": self.outputBucket,
            "OutputKey": f"skills/{skillId}/derived/transcribe/{videoId}/provider.json"
        }
        if sourceLanguage == "auto":
            request["IdentifyLanguage"] = True
            request["LanguageOptions"] = list(self.LANGUAGE_CODES.values())
        elif sourceLanguage in self.LANGUAGE_CODES:
            request["LanguageCode"] = self.LANGUAGE_CODES[sourceLanguage]
        else:
            raise ValueError(f"Unsupported source language: {sourceLanguage}")

        try:
            response = self._getTranscribeClient().start_transcription_job(**request)
        except Exception as exc:
            raise self._providerError(exc) from exc
        return self._normalizeJob(jobName, response.get("TranscriptionJob", {}))

    def getTranscriptionStatus(self, jobName: str) -> TranscriptionJobStatus:
        try:
            response = self._getTranscribeClient().get_transcription_job(
                TranscriptionJobName=jobName
            )
        except Exception as exc:
            providerError = self._providerError(exc)
            if providerError.code == "notFound":
                return TranscriptionJobStatus(jobName, TranscriptionState.NOT_FOUND)
            raise providerError from exc
        return self._normalizeJob(jobName, response.get("TranscriptionJob", {}))

    def completeTranscription(
        self,
        status: TranscriptionJobStatus,
        videoId: str,
        skillId: str,
        storageAdapter: StorageAdapter
    ) -> Tuple[Optional[str], List[TranscriptSegment]]:
        if status.state in (TranscriptionState.QUEUED, TranscriptionState.IN_PROGRESS):
            raise TranscriptionPendingError(status.jobName, status.state)
        if status.state == TranscriptionState.FAILED:
            raise TranscriptionProviderError(
                "failed",
                status.failureReason or f"Transcription job {status.jobName} failed"
            )
        if status.state != TranscriptionState.COMPLETED:
            raise TranscriptionProviderError(
                "invalidState",
                f"Transcription job {status.jobName} is not complete"
            )

        data = self._loadTranscript(status.transcriptUri)
        segments = self._parseTranscriptItems(data, status.languageCode)
        if not segments:
            return None, []

        transcriptKey = f"skills/{skillId}/derived/transcripts/{videoId}.json"
        payload = {
            "schemaVersion": 1,
            "videoId": videoId,
            "languageCode": status.languageCode,
            "segments": [segment.toDict() for segment in segments]
        }
        storageAdapter.writeAsset(transcriptKey, json.dumps(payload, indent=2).encode("utf-8"))
        return transcriptKey, segments

    def transcribe(
        self,
        videoId: str,
        skillId: str,
        localFilePath: Optional[Path],
        storageAdapter: StorageAdapter,
        sourceKey: Optional[str] = None,
        sourceLanguage: str = "auto"
    ) -> Tuple[Optional[str], List[TranscriptSegment]]:
        del localFilePath
        jobName = self.buildJobName(skillId, videoId)
        status = self.getTranscriptionStatus(jobName)
        if status.state == TranscriptionState.NOT_FOUND:
            status = self.startTranscription(
                videoId,
                skillId,
                sourceKey or "",
                sourceLanguage
            )
        if status.state in (TranscriptionState.QUEUED, TranscriptionState.IN_PROGRESS):
            raise TranscriptionPendingError(status.jobName, status.state)
        return self.completeTranscription(status, videoId, skillId, storageAdapter)

    def _normalizeJob(self, jobName: str, job: Dict[str, Any]) -> TranscriptionJobStatus:
        providerStatus = job.get("TranscriptionJobStatus")
        states = {
            "QUEUED": TranscriptionState.QUEUED,
            "IN_PROGRESS": TranscriptionState.IN_PROGRESS,
            "COMPLETED": TranscriptionState.COMPLETED,
            "FAILED": TranscriptionState.FAILED
        }
        if providerStatus not in states:
            raise TranscriptionProviderError(
                "invalidResponse",
                f"Amazon Transcribe returned unknown status: {providerStatus}"
            )
        return TranscriptionJobStatus(
            jobName=jobName,
            state=states[providerStatus],
            transcriptUri=job.get("Transcript", {}).get("TranscriptFileUri"),
            languageCode=job.get("LanguageCode"),
            failureReason=job.get("FailureReason")
        )

    def _providerError(self, exc: Exception) -> TranscriptionProviderError:
        response = getattr(exc, "response", {})
        error = response.get("Error", {}) if isinstance(response, dict) else {}
        providerCode = str(error.get("Code", exc.__class__.__name__))
        message = str(error.get("Message", str(exc)))
        normalized = providerCode.lower()
        if "notfound" in normalized or "badrequest" in normalized and "not found" in message.lower():
            code = "notFound"
        elif "accessdenied" in normalized or "unauthorized" in normalized:
            code = "accessDenied"
        elif "throttl" in normalized or "limitexceeded" in normalized:
            code = "throttled"
        elif "timeout" in normalized:
            code = "timedOut"
        else:
            code = "providerError"
        return TranscriptionProviderError(code, f"Amazon Transcribe {code}: {message}")

    def _loadTranscript(self, transcriptUri: Optional[str]) -> Dict[str, Any]:
        if not transcriptUri:
            raise TranscriptionProviderError("invalidResponse", "Completed job has no transcript URI")
        try:
            if transcriptUri.lstrip().startswith("{"):
                data = json.loads(transcriptUri)
            else:
                parsed = urlparse(transcriptUri)
                if parsed.scheme == "s3":
                    bucket = parsed.netloc
                    key = unquote(parsed.path.lstrip("/"))
                elif parsed.scheme in ("http", "https"):
                    bucket = self.outputBucket
                    key = unquote(parsed.path.lstrip("/"))
                    if key.startswith(f"{bucket}/"):
                        key = key[len(bucket) + 1:]
                else:
                    bucket = self.outputBucket
                    key = transcriptUri.lstrip("/")
                response = self._getS3Client().get_object(Bucket=bucket, Key=key)
                raw = response["Body"].read()
                data = json.loads(raw)
        except TranscriptionProviderError:
            raise
        except Exception as exc:
            raise TranscriptionProviderError(
                "invalidTranscript",
                f"Could not load completed transcript: {exc}"
            ) from exc
        if not isinstance(data, dict) or not isinstance(data.get("results"), dict):
            raise TranscriptionProviderError("invalidTranscript", "Transcript JSON is malformed")
        return data

    def _parseTranscriptItems(
        self,
        data: Dict[str, Any],
        languageCode: Optional[str]
    ) -> List[TranscriptSegment]:
        items = data["results"].get("items", [])
        if not isinstance(items, list):
            raise TranscriptionProviderError("invalidTranscript", "Transcript items must be an array")
        segments: List[TranscriptSegment] = []
        for item in items:
            if not isinstance(item, dict) or item.get("type") != "pronunciation":
                continue
            try:
                startMs = int(float(item["start_time"]) * 1000)
                endMs = int(float(item["end_time"]) * 1000)
                alternative = item["alternatives"][0]
                text = str(alternative["content"]).strip()
                confidence = float(alternative.get("confidence", 0.0))
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise TranscriptionProviderError(
                    "invalidTranscript",
                    f"Transcript word timing is malformed: {exc}"
                ) from exc
            if not text or endMs <= startMs or not 0.0 <= confidence <= 1.0:
                raise TranscriptionProviderError(
                    "invalidTranscript",
                    "Transcript word contains invalid text, timing, or confidence"
                )
            segments.append(
                TranscriptSegment(startMs, endMs, text, confidence, languageCode)
            )
        return segments
