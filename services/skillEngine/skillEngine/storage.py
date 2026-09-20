from typing import Any, Optional


class StorageAdapter:
    def readAsset(self, key: str) -> bytes:
        raise NotImplementedError("Subclasses must implement readAsset")

    def writeAsset(self, key: str, data: bytes) -> str:
        raise NotImplementedError("Subclasses must implement writeAsset")

    def assetExists(self, key: str) -> bool:
        raise NotImplementedError("Subclasses must implement assetExists")


class S3StorageAdapter(StorageAdapter):
    def __init__(
        self,
        bucket: str,
        s3Client: Optional[Any] = None,
        maxReadBytes: int = 20 * 1024 * 1024,
    ) -> None:
        if not bucket:
            raise ValueError("S3 bucket is required")
        if maxReadBytes < 1:
            raise ValueError("maxReadBytes must be positive")
        self.bucket = bucket
        self.s3Client = s3Client
        self.maxReadBytes = maxReadBytes

    def _getClient(self) -> Any:
        if self.s3Client is not None:
            return self.s3Client
        import boto3
        return boto3.client("s3")

    @staticmethod
    def _validateKey(key: str) -> None:
        if not key or key.startswith("/") or ".." in key.split("/"):
            raise ValueError("Invalid storage key")

    def readAsset(self, key: str) -> bytes:
        self._validateKey(key)
        response = self._getClient().get_object(Bucket=self.bucket, Key=key)
        declaredSize = response.get("ContentLength")
        if isinstance(declaredSize, int) and declaredSize > self.maxReadBytes:
            response["Body"].close()
            raise ValueError(f"S3 object exceeds {self.maxReadBytes} bytes: {key}")
        body = response["Body"]
        chunks = []
        total = 0
        try:
            while True:
                chunk = body.read(min(64 * 1024, self.maxReadBytes - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > self.maxReadBytes:
                    raise ValueError(f"S3 object exceeds {self.maxReadBytes} bytes: {key}")
                chunks.append(chunk)
        finally:
            body.close()
        return b"".join(chunks)

    def writeAsset(self, key: str, data: bytes) -> str:
        self._validateKey(key)
        if not isinstance(data, bytes):
            raise TypeError("Storage payload must be bytes")
        contentType = "application/octet-stream"
        if key.endswith(".json"):
            contentType = "application/json"
        elif key.endswith(".mp3"):
            contentType = "audio/mpeg"
        elif key.endswith(".txt"):
            contentType = "text/plain; charset=utf-8"
        self._getClient().put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=contentType,
            ServerSideEncryption="AES256",
        )
        return key

    def assetExists(self, key: str) -> bool:
        self._validateKey(key)
        try:
            self._getClient().head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:
            response = getattr(exc, "response", {})
            code = str(response.get("Error", {}).get("Code", ""))
            status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in {"404", "NoSuchKey", "NotFound"} or status == 404:
                return False
            raise
