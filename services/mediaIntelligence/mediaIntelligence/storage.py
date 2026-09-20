from dataclasses import dataclass
import os
from pathlib import Path
import re
import tempfile
from typing import Any, BinaryIO, List, Optional

from .errors import (
    StorageAccessDeniedError,
    StorageError,
    StorageLimitError,
    StorageNotFoundError,
    StorageTransientError,
)


DEFAULT_MAX_OBJECT_BYTES = 250 * 1024 * 1024
DEFAULT_MAX_READ_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_STAGING_BYTES = 750 * 1024 * 1024
STREAM_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True)
class ObjectMetadata:
    contentLength: int
    contentType: Optional[str] = None
    eTag: Optional[str] = None


def validateStorageKey(key: str) -> str:
    if not isinstance(key, str) or not key or key.startswith(("/", "\\")):
        raise ValueError("Storage key must be a non-empty relative key")
    if "\\" in key:
        raise ValueError(f"Storage key must use forward slashes: {key}")
    parts = key.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"Storage path traversal or invalid segment detected: {key}")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", key):
        raise ValueError(f"Storage key contains unsupported or ambiguous characters: {key}")
    return key


def validateOwnedSourceKey(skillId: str, key: str, assetType: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", skillId):
        raise ValueError(f"Invalid skill identifier for storage ownership: {skillId}")
    if assetType not in {"videos", "images", "documents"}:
        raise ValueError(f"Unsupported asset type for storage ownership: {assetType}")
    validateStorageKey(key)
    expectedPrefix = f"skills/{skillId}/source/{assetType}/"
    if not key.startswith(expectedPrefix):
        raise ValueError(
            f"Storage key '{key}' is not owned by skill '{skillId}' under '{expectedPrefix}'"
        )
    return key


def _providerErrorCode(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error", {})
        if isinstance(error, dict):
            return str(error.get("Code", ""))
    return ""


def _raiseStorageProviderError(exc: Exception, operation: str, key: str) -> None:
    code = _providerErrorCode(exc)
    if code in {"404", "NoSuchKey", "NotFound", "NoSuchBucket"}:
        raise StorageNotFoundError(f"S3 object not found during {operation}: {key}") from exc
    if code in {"403", "AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch"}:
        raise StorageAccessDeniedError(f"S3 access denied during {operation}: {key}") from exc
    if code in {
        "SlowDown", "Throttling", "ThrottlingException", "RequestLimitExceeded",
        "ServiceUnavailable", "InternalError",
    }:
        raise StorageTransientError(f"Transient S3 failure during {operation} for {key}: {code}") from exc
    raise StorageError(f"S3 {operation} failed for {key}: {code or type(exc).__name__}") from exc


def _closeBody(body: Any) -> None:
    close = getattr(body, "close", None)
    if callable(close):
        close()


class StorageAdapter:
    """Abstract storage adapter for bounded media asset access."""

    def getObjectMetadata(self, key: str) -> ObjectMetadata:
        raise NotImplementedError("Subclasses must implement getObjectMetadata")

    def readAsset(self, key: str, maxBytes: int = DEFAULT_MAX_READ_BYTES) -> bytes:
        raise NotImplementedError("Subclasses must implement readAsset")

    def writeAsset(self, key: str, data: bytes) -> str:
        raise NotImplementedError("Subclasses must implement writeAsset")

    def assetExists(self, key: str) -> bool:
        try:
            self.getObjectMetadata(key)
            return True
        except StorageNotFoundError:
            return False

    def resolveLocalPath(self, key: str) -> Optional[Path]:
        return None

    def cleanup(self) -> None:
        pass


class LocalStorageAdapter(StorageAdapter):
    """Filesystem adapter strictly confined to one explicitly configured root."""

    def __init__(self, assetRoot: Optional[Path] = None) -> None:
        self.assetRoot = Path(assetRoot if assetRoot is not None else Path.cwd()).resolve()
        self.assetRoot.mkdir(parents=True, exist_ok=True)

    def _resolveSafePath(self, key: str) -> Path:
        validateStorageKey(key)
        normalized = os.path.normpath(key).replace("\\", "/")
        targetPath = (self.assetRoot / normalized).resolve()
        try:
            targetPath.relative_to(self.assetRoot)
        except ValueError as exc:
            raise ValueError(f"Storage path traversal detected for key: {key}") from exc
        return targetPath

    def getObjectMetadata(self, key: str) -> ObjectMetadata:
        targetPath = self._resolveSafePath(key)
        if not targetPath.is_file():
            raise StorageNotFoundError(f"Asset not found in local storage root: {key}")
        return ObjectMetadata(contentLength=targetPath.stat().st_size)

    def readAsset(self, key: str, maxBytes: int = DEFAULT_MAX_READ_BYTES) -> bytes:
        metadata = self.getObjectMetadata(key)
        if metadata.contentLength > maxBytes:
            raise StorageLimitError(
                f"Asset '{key}' size {metadata.contentLength} bytes exceeds read limit of {maxBytes} bytes"
            )
        chunks: List[bytes] = []
        actualBytes = 0
        with self._resolveSafePath(key).open("rb") as source:
            while True:
                chunk = source.read(STREAM_CHUNK_BYTES)
                if not chunk:
                    break
                actualBytes += len(chunk)
                if actualBytes > maxBytes or actualBytes > metadata.contentLength:
                    raise StorageLimitError(
                        f"Asset '{key}' changed or exceeded its limit while being read"
                    )
                chunks.append(chunk)
        if actualBytes != metadata.contentLength:
            raise StorageError(
                f"Asset '{key}' read {actualBytes} bytes; expected {metadata.contentLength} bytes"
            )
        return b"".join(chunks)

    def writeAsset(self, key: str, data: bytes) -> str:
        targetPath = self._resolveSafePath(key)
        targetPath.parent.mkdir(parents=True, exist_ok=True)
        targetPath.write_bytes(data)
        return key

    def resolveLocalPath(self, key: str) -> Optional[Path]:
        targetPath = self._resolveSafePath(key)
        return targetPath if targetPath.is_file() else None


class S3StorageAdapter(StorageAdapter):
    """S3 adapter with bounded reads, downloads, and staging disk usage."""

    MAX_REMOTE_BYTES = DEFAULT_MAX_OBJECT_BYTES

    def __init__(
        self,
        bucketName: str,
        s3Client: Optional[Any] = None,
        maxObjectBytes: int = DEFAULT_MAX_OBJECT_BYTES,
        maxReadBytes: int = DEFAULT_MAX_READ_BYTES,
        maxStagingBytes: int = DEFAULT_MAX_STAGING_BYTES,
        stagingDirectory: Optional[Path] = None,
    ) -> None:
        if not bucketName:
            raise ValueError("S3 bucket name is required")
        if min(maxObjectBytes, maxReadBytes, maxStagingBytes) <= 0:
            raise ValueError("S3 byte limits must be positive")
        self.bucketName = bucketName
        self._client = s3Client
        self.maxObjectBytes = maxObjectBytes
        self.maxReadBytes = maxReadBytes
        self.maxStagingBytes = maxStagingBytes
        self._stagedFiles: List[Path] = []
        self._stagedBytes = 0
        self._ownedStagingDirectory = stagingDirectory is None
        if stagingDirectory is None:
            self._stagingDirectory = Path(tempfile.mkdtemp(prefix="skilltwin-media-"))
        else:
            self._stagingDirectory = Path(stagingDirectory).resolve()
            self._stagingDirectory.mkdir(parents=True, exist_ok=True)

    def _getClient(self) -> Any:
        if self._client is not None:
            return self._client
        import boto3
        return boto3.client("s3")

    def getObjectMetadata(self, key: str) -> ObjectMetadata:
        validateStorageKey(key)
        try:
            response = self._getClient().head_object(Bucket=self.bucketName, Key=key)
        except Exception as exc:
            _raiseStorageProviderError(exc, "head_object", key)
        contentLength = response.get("ContentLength")
        if not isinstance(contentLength, int) or contentLength < 0:
            raise StorageError(f"S3 returned invalid ContentLength for {key}")
        return ObjectMetadata(
            contentLength=contentLength,
            contentType=response.get("ContentType"),
            eTag=response.get("ETag"),
        )

    def _openObject(self, key: str) -> BinaryIO:
        try:
            response = self._getClient().get_object(Bucket=self.bucketName, Key=key)
            body = response.get("Body")
            if body is None or not hasattr(body, "read"):
                raise StorageError(f"S3 returned no readable body for {key}")
            return body
        except StorageError:
            raise
        except Exception as exc:
            _raiseStorageProviderError(exc, "get_object", key)

    def readAsset(self, key: str, maxBytes: int = DEFAULT_MAX_READ_BYTES) -> bytes:
        metadata = self.getObjectMetadata(key)
        effectiveLimit = min(maxBytes, self.maxReadBytes)
        if metadata.contentLength > effectiveLimit:
            raise StorageLimitError(
                f"S3 object '{key}' size {metadata.contentLength} bytes exceeds read limit of {effectiveLimit} bytes"
            )
        body = self._openObject(key)
        chunks: List[bytes] = []
        actualBytes = 0
        try:
            while True:
                chunk = body.read(STREAM_CHUNK_BYTES)
                if not chunk:
                    break
                actualBytes += len(chunk)
                if actualBytes > effectiveLimit or actualBytes > metadata.contentLength:
                    raise StorageLimitError(f"S3 object '{key}' exceeded its declared or allowed byte length")
                chunks.append(chunk)
        except StorageLimitError:
            raise
        except Exception as exc:
            _raiseStorageProviderError(exc, "stream read", key)
        finally:
            _closeBody(body)
        if actualBytes != metadata.contentLength:
            raise StorageError(
                f"S3 object '{key}' streamed {actualBytes} bytes; expected {metadata.contentLength} bytes"
            )
        return b"".join(chunks)

    def writeAsset(self, key: str, data: bytes) -> str:
        validateStorageKey(key)
        try:
            self._getClient().put_object(Bucket=self.bucketName, Key=key, Body=data)
        except Exception as exc:
            _raiseStorageProviderError(exc, "put_object", key)
        return key

    def resolveLocalPath(self, key: str) -> Optional[Path]:
        validateStorageKey(key)
        if not self._stagingDirectory.is_dir():
            if self._ownedStagingDirectory:
                self._stagingDirectory = Path(tempfile.mkdtemp(prefix="skilltwin-media-"))
            else:
                self._stagingDirectory.mkdir(parents=True, exist_ok=True)
        metadata = self.getObjectMetadata(key)
        if metadata.contentLength <= 0:
            raise StorageLimitError(f"S3 object '{key}' is empty")
        if metadata.contentLength > self.maxObjectBytes:
            raise StorageLimitError(
                f"S3 object '{key}' size {metadata.contentLength} bytes exceeds limit of {self.maxObjectBytes} bytes"
            )
        if self._stagedBytes + metadata.contentLength > self.maxStagingBytes:
            raise StorageLimitError(
                f"Staging '{key}' would exceed disk budget of {self.maxStagingBytes} bytes"
            )

        suffix = Path(key).suffix or ".media"
        with tempfile.NamedTemporaryFile(
            suffix=suffix, prefix="download-", dir=self._stagingDirectory, delete=False,
        ) as tmp:
            tempPath = Path(tmp.name)

        body: Optional[BinaryIO] = None
        actualBytes = 0
        try:
            body = self._openObject(key)
            with tempPath.open("wb") as output:
                while True:
                    chunk = body.read(STREAM_CHUNK_BYTES)
                    if not chunk:
                        break
                    actualBytes += len(chunk)
                    if actualBytes > self.maxObjectBytes or actualBytes > metadata.contentLength:
                        raise StorageLimitError(
                            f"S3 object '{key}' exceeded its declared or allowed byte length while staging"
                        )
                    output.write(chunk)
            if actualBytes != metadata.contentLength:
                raise StorageError(
                    f"S3 object '{key}' streamed {actualBytes} bytes; expected {metadata.contentLength} bytes"
                )
            self._stagedFiles.append(tempPath)
            self._stagedBytes += actualBytes
            return tempPath
        except (StorageError, StorageLimitError):
            if tempPath.is_file():
                tempPath.unlink()
            raise
        except Exception as exc:
            if tempPath.is_file():
                tempPath.unlink()
            _raiseStorageProviderError(exc, "stream download", key)
        finally:
            if body is not None:
                _closeBody(body)

    def cleanup(self) -> None:
        failures: List[str] = []
        for path in self._stagedFiles:
            try:
                if path.is_file():
                    path.unlink()
            except OSError as exc:
                failures.append(f"{path}: {exc}")
        self._stagedFiles.clear()
        self._stagedBytes = 0
        if self._ownedStagingDirectory:
            try:
                self._stagingDirectory.rmdir()
            except FileNotFoundError:
                pass
            except OSError as exc:
                failures.append(f"{self._stagingDirectory}: {exc}")
        if failures:
            raise StorageError("Failed to clean staged media: " + "; ".join(failures))
