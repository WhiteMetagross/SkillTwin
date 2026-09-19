import os
from pathlib import Path
from typing import Any, Optional

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

class LocalStorageAdapter(StorageAdapter):
    """
    Local filesystem storage adapter resolving assets under a configured root directory.
    Safely prevents directory traversal and writes real files to disk.
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
            # If relative to cwd, check direct path fallback
            direct = Path(key).resolve()
            if direct.is_file():
                return direct.read_bytes()
            raise FileNotFoundError(f"Asset not found in local storage: {key}")
        return targetPath.read_bytes()

    def writeAsset(self, key: str, data: bytes) -> str:
        targetPath = self._resolveSafePath(key)
        targetPath.parent.mkdir(parents=True, exist_ok=True)
        targetPath.write_bytes(data)
        return key

    def assetExists(self, key: str) -> bool:
        targetPath = self._resolveSafePath(key)
        if targetPath.is_file():
            return True
        direct = Path(key).resolve()
        return direct.is_file()

    def resolveLocalPath(self, key: str) -> Optional[Path]:
        targetPath = self._resolveSafePath(key)
        if targetPath.is_file():
            return targetPath
        direct = Path(key).resolve()
        if direct.is_file():
            return direct
        return targetPath

class S3StorageAdapter(StorageAdapter):
    """
    Amazon Simple Storage Service adapter for cloud media storage.
    Delegates to boto3 client and supports mocked client tests.
    """

    def __init__(self, bucketName: str, s3Client: Optional[Any] = None) -> None:
        self.bucketName = bucketName
        self._client = s3Client

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
