import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mediaIntelligence.errors import (
    StorageAccessDeniedError,
    StorageError,
    StorageLimitError,
    StorageTransientError,
)
from mediaIntelligence.storage import S3StorageAdapter, validateStorageKey


class ProviderError(Exception):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}


class PartialFailureBody:
    def __init__(self) -> None:
        self.calls = 0
        self.closed = False

    def read(self, _size: int) -> bytes:
        self.calls += 1
        if self.calls == 1:
            return b"partial"
        raise OSError("connection reset")

    def close(self) -> None:
        self.closed = True


def testOversizeS3ObjectRejectedBeforeDownload(tmp_path: Path) -> None:
    client = MagicMock()
    client.head_object.return_value = {"ContentLength": 101}
    adapter = S3StorageAdapter(
        "bucket", client, maxObjectBytes=100, stagingDirectory=tmp_path,
    )
    with pytest.raises(StorageLimitError, match="exceeds limit"):
        adapter.resolveLocalPath("skills/s1/source/videos/v.mp4")
    client.get_object.assert_not_called()


def testStreamExceedingDeclaredLengthRemovesPartialFile(tmp_path: Path) -> None:
    client = MagicMock()
    client.head_object.return_value = {"ContentLength": 3}
    client.get_object.return_value = {"Body": io.BytesIO(b"four")}
    adapter = S3StorageAdapter("bucket", client, stagingDirectory=tmp_path)
    with pytest.raises(StorageLimitError, match="declared or allowed"):
        adapter.resolveLocalPath("skills/s1/source/videos/v.mp4")
    assert list(tmp_path.iterdir()) == []


def testStreamExceedingAllowedLengthRemovesPartialFile(tmp_path: Path) -> None:
    client = MagicMock()
    client.head_object.return_value = {"ContentLength": 4}
    client.get_object.return_value = {"Body": io.BytesIO(b"12345")}
    adapter = S3StorageAdapter(
        "bucket", client, maxObjectBytes=4, stagingDirectory=tmp_path,
    )
    with pytest.raises(StorageLimitError, match="declared or allowed"):
        adapter.resolveLocalPath("skills/s1/source/videos/v.mp4")
    assert list(tmp_path.iterdir()) == []


def testPartialS3DownloadFailureCleansTemporaryFile(tmp_path: Path) -> None:
    client = MagicMock()
    body = PartialFailureBody()
    client.head_object.return_value = {"ContentLength": 20}
    client.get_object.return_value = {"Body": body}
    adapter = S3StorageAdapter("bucket", client, stagingDirectory=tmp_path)
    with pytest.raises(StorageError, match="stream download"):
        adapter.resolveLocalPath("skills/s1/source/videos/v.mp4")
    assert body.closed is True
    assert list(tmp_path.iterdir()) == []


def testS3AccessDeniedIsNotReportedAsMissing(tmp_path: Path) -> None:
    client = MagicMock()
    client.head_object.side_effect = ProviderError("AccessDenied")
    adapter = S3StorageAdapter("bucket", client, stagingDirectory=tmp_path)
    with pytest.raises(StorageAccessDeniedError):
        adapter.assetExists("skills/s1/source/videos/v.mp4")


def testS3ThrottlingIsExplicit(tmp_path: Path) -> None:
    client = MagicMock()
    client.head_object.side_effect = ProviderError("SlowDown")
    adapter = S3StorageAdapter("bucket", client, stagingDirectory=tmp_path)
    with pytest.raises(StorageTransientError):
        adapter.getObjectMetadata("skills/s1/source/videos/v.mp4")


def testStagingDiskBudgetIncludesPreviouslyStagedFiles(tmp_path: Path) -> None:
    client = MagicMock()
    client.head_object.return_value = {"ContentLength": 4}
    client.get_object.return_value = {"Body": io.BytesIO(b"1234")}
    adapter = S3StorageAdapter(
        "bucket", client, maxObjectBytes=10, maxStagingBytes=7,
        stagingDirectory=tmp_path,
    )
    first = adapter.resolveLocalPath("skills/s1/source/videos/one.mp4")
    assert first is not None and first.is_file()
    with pytest.raises(StorageLimitError, match="disk budget"):
        adapter.resolveLocalPath("skills/s1/source/videos/two.mp4")
    adapter.cleanup()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("key", ["skills/s1/video name.mp4", "skills/s1/video.mp4?x=1", "skills//v.mp4"])
def testAmbiguousStorageKeysAreRejected(key: str) -> None:
    with pytest.raises(ValueError, match="unsupported|traversal"):
        validateStorageKey(key)
