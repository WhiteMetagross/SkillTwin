import os
from pathlib import Path
import tempfile
from typing import Any, BinaryIO, List, Optional

class StorageAdapter:
    """
    Abstract storage adapter for reading and writing media intelligence assets.
    """

    def readAsset(self, key: str) -> bytes:
        raise NotImplementedError("Subclasses must implement readAsset")

    def writeAsset(self, key: str, data: bytes) -> str:
        raise NotImplementedError("Subclasses must implement writeAsset")

    def assetExists(self, key: str) -> bool:
        raise NotImplementedError("Subclasses must implement assetExists")

    def resolveLocalPath(self, key: str) -> Optional[Path]:
        return None

    def cleanup(self) -> None:
        pass

class LocalStorageAdapter(StorageAdapter):
    """
    Local filesystem storage adapter resolving assets strictly under a configured root directory.
    Prevents directory traversal and never falls back to the process working directory.
    """

    def __init__(self, assetRoot: Optional[Path] = None) -> None:
        if assetRoot is not None:
            self.assetRoot = Path(assetRoot).resolve()
        else:
            self.assetRoot = Path.cwd().resolve()
        self.assetRoot.mkdir(parents=True, exist_ok=True)

    def _resolveSafePath(self, key: str) -> Path:
        normalized = os.path.normpath(key).lstrip("\\/").replace("\\", "/")
        targetPath = (self.assetRoot / normalized).resolve()
        try:
            targetPath.relative_to(self.assetRoot)
        except ValueError:
            raise ValueError(f"Storage path traversal detected for key: {key}")
        return targetPath

    def readAsset(self, key: str) -> bytes:
        targetPath = self._resolveSafePath(key)
        if not targetPath.is_file():
            raise FileNotFoundError(f"Asset not found in local storage root: {key}")
        return targetPath.read_bytes()

    def writeAsset(self, key: str, data: bytes) -> str:
        targetPath = self._resolveSafePath(key)
        targetPath.parent.mkdir(parents=True, exist_ok=True)
        targetPath.write_bytes(data)
        return key

    def assetExists(self, key: str) -> bool:
        try:
            targetPath = self._resolveSafePath(key)
            return targetPath.is_file()
        except ValueError:
            return False

    def resolveLocalPath(self, key: str) -> Optional[Path]:
        try:
            targetPath = self._resolveSafePath(key)
            if targetPath.is_file():
                return targetPath
            return None
        except ValueError:
            return None

class S3StorageAdapter(StorageAdapter):
    """
    Amazon Simple Storage Service adapter for cloud media storage.
    Stages remote media into bounded local temporary files for inspection and frame sampling.
    """

    MAX_REMOTE_BYTES = 262144000  # 250 megabytes
    MAX_STAGING_BYTES = MAX_REMOTE_BYTES * 3
    READ_CHUNK_BYTES = 65536

    def __init__(
        self,
        bucketName: str,
        s3Client: Optional[Any] = None,
        allowedPrefix: Optional[str] = None,
        stagingRoot: Optional[Path] = None
    ) -> None:
        if not bucketName:
            raise ValueError("S3 bucket name is required")
        self.bucketName = bucketName
        self._client = s3Client
        self.allowedPrefix = allowedPrefix.rstrip("/") + "/" if allowedPrefix else None
        self.stagingRoot = Path(stagingRoot).resolve() if stagingRoot else None
        if self.stagingRoot:
            self.stagingRoot.mkdir(parents=True, exist_ok=True)
        self._stagedFiles: List[Path] = []
        self._stagedBytes = 0

    def _validateKey(self, key: str) -> str:
        normalized = key.replace("\\", "/").lstrip("/")
        parts = normalized.split("/")
        if not normalized or any(part in ("", ".", "..") for part in parts):
            raise ValueError(f"Invalid S3 object key: {key}")
        if self.allowedPrefix and not normalized.startswith(self.allowedPrefix):
            raise ValueError(
                f"S3 object key '{key}' is outside allowed prefix '{self.allowedPrefix}'"
            )
        return normalized

    def _copyBounded(self, body: Any, sink: BinaryIO, byteLimit: int) -> int:
        written = 0
        while True:
            chunk = body.read(self.READ_CHUNK_BYTES)
            if not chunk:
                break
            written += len(chunk)
            if written > byteLimit:
                raise ValueError(f"S3 object exceeded byte limit of {byteLimit}")
            sink.write(chunk)
        return written

    def _getClient(self) -> Any:
        if self._client is not None:
            return self._client
        import boto3
        return boto3.client("s3")

    def readAsset(self, key: str) -> bytes:
        key = self._validateKey(key)
        client = self._getClient()
        response = client.get_object(Bucket=self.bucketName, Key=key)
        body = response["Body"]
        try:
            from io import BytesIO
            buffer = BytesIO()
            self._copyBounded(body, buffer, self.MAX_REMOTE_BYTES)
            return buffer.getvalue()
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()

    def writeAsset(self, key: str, data: bytes) -> str:
        key = self._validateKey(key)
        client = self._getClient()
        client.put_object(Bucket=self.bucketName, Key=key, Body=data)
        return key

    def assetExists(self, key: str) -> bool:
        client = self._getClient()
        try:
            key = self._validateKey(key)
            client.head_object(Bucket=self.bucketName, Key=key)
            return True
        except Exception:
            return False

    def resolveLocalPath(self, key: str) -> Optional[Path]:
        """
        Stages remote S3 video or asset into a bounded temporary file for decoding.
        Validates size limit and tracks file for cleanup.
        """
        key = self._validateKey(key)
        client = self._getClient()
        tempPath: Optional[Path] = None
        body: Optional[Any] = None
        try:
            head = client.head_object(Bucket=self.bucketName, Key=key)
            contentLength = head.get("ContentLength", 0)
            if not isinstance(contentLength, int) or contentLength <= 0:
                raise ValueError(f"Remote asset '{key}' has an invalid content length")
            if contentLength > self.MAX_REMOTE_BYTES:
                raise ValueError(
                    f"Remote asset '{key}' size {contentLength} bytes exceeds limit of {self.MAX_REMOTE_BYTES} bytes"
                )
            if self._stagedBytes + contentLength > self.MAX_STAGING_BYTES:
                raise ValueError("Total temporary staging disk limit exceeded")

            suffix = Path(key).suffix or ".mp4"
            with tempfile.NamedTemporaryFile(
                suffix=suffix,
                delete=False,
                dir=self.stagingRoot
            ) as tmp:
                tempPath = Path(tmp.name)

                response = client.get_object(Bucket=self.bucketName, Key=key)
                body = response["Body"]
                actualLength = self._copyBounded(body, tmp, self.MAX_REMOTE_BYTES)

            if actualLength != contentLength:
                raise ValueError(
                    f"Remote asset '{key}' downloaded {actualLength} bytes, expected {contentLength}"
                )

            self._stagedFiles.append(tempPath)
            self._stagedBytes += actualLength
            return tempPath
        except Exception:
            if tempPath and tempPath.is_file():
                tempPath.unlink()
            raise
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()

    def cleanup(self) -> None:
        for p in self._stagedFiles:
            try:
                if p.is_file():
                    p.unlink()
            except Exception:
                pass
        self._stagedFiles.clear()
        self._stagedBytes = 0
