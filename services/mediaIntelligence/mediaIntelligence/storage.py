import os
from pathlib import Path
import tempfile
from typing import Any, List, Optional

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

    def __init__(self, bucketName: str, s3Client: Optional[Any] = None) -> None:
        self.bucketName = bucketName
        self._client = s3Client
        self._stagedFiles: List[Path] = []

    def _getClient(self) -> Any:
        if self._client is not None:
            return self._client
        import boto3
        return boto3.client("s3")

    def readAsset(self, key: str) -> bytes:
        client = self._getClient()
        response = client.get_object(Bucket=self.bucketName, Key=key)
        return response["Body"].read()

    def writeAsset(self, key: str, data: bytes) -> str:
        client = self._getClient()
        client.put_object(Bucket=self.bucketName, Key=key, Body=data)
        return key

    def assetExists(self, key: str) -> bool:
        client = self._getClient()
        try:
            client.head_object(Bucket=self.bucketName, Key=key)
            return True
        except Exception:
            return False

    def resolveLocalPath(self, key: str) -> Optional[Path]:
        """
        Stages remote S3 video or asset into a bounded temporary file for decoding.
        Validates size limit and tracks file for cleanup.
        """
        client = self._getClient()
        try:
            head = client.head_object(Bucket=self.bucketName, Key=key)
            contentLength = head.get("ContentLength", 0)
            if contentLength > self.MAX_REMOTE_BYTES:
                raise ValueError(
                    f"Remote asset '{key}' size {contentLength} bytes exceeds limit of {self.MAX_REMOTE_BYTES} bytes"
                )

            # Stage into temporary file
            suffix = Path(key).suffix or ".mp4"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tempPath = Path(tmp.name)

            response = client.get_object(Bucket=self.bucketName, Key=key)
            body = response["Body"]
            with open(tempPath, "wb") as f:
                while True:
                    chunk = body.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)

            self._stagedFiles.append(tempPath)
            return tempPath
        except Exception as exc:
            if isinstance(exc, ValueError):
                raise
            return None

    def cleanup(self) -> None:
        for p in self._stagedFiles:
            try:
                if p.is_file():
                    p.unlink()
            except Exception:
                pass
        self._stagedFiles.clear()
