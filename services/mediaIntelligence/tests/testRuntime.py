from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mediaIntelligence.bedrockObserver import BedrockObserver
from mediaIntelligence.errors import RuntimeConfigurationError
from mediaIntelligence.runtime import ProductionConfig, createProductionRuntime
from mediaIntelligence.storage import S3StorageAdapter
from mediaIntelligence.transcriber import AmazonTranscribeService


def executableEnvironment(tmp_path: Path) -> dict[str, str]:
    ffmpeg = tmp_path / "ffmpeg"
    ffprobe = tmp_path / "ffprobe"
    ffmpeg.write_bytes(b"binary")
    ffprobe.write_bytes(b"binary")
    return {
        "AWS_REGION": "ap-south-1",
        "S3_MEDIA_BUCKET": "skilltwin-media-test",
        "BEDROCK_OBSERVER_MODEL_ID": "model-id",
        "FFMPEG_PATH": str(ffmpeg),
        "FFPROBE_PATH": str(ffprobe),
    }


def testProductionConfigurationMissingFailsFast() -> None:
    with pytest.raises(RuntimeConfigurationError, match="AWS_REGION.*BEDROCK.*S3_MEDIA_BUCKET"):
        ProductionConfig.fromEnvironment({})


def testProductionConfigurationRequiresMediaBinaries(tmp_path: Path) -> None:
    env = {
        "AWS_REGION": "ap-south-1",
        "S3_MEDIA_BUCKET": "bucket",
        "BEDROCK_OBSERVER_MODEL_ID": "model",
        "FFMPEG_PATH": str(tmp_path / "missing-ffmpeg"),
        "FFPROBE_PATH": str(tmp_path / "missing-ffprobe"),
    }
    with pytest.raises(RuntimeConfigurationError, match="ffmpeg.*ffprobe"):
        ProductionConfig.fromEnvironment(env)


def testProductionRuntimeConstructsNoLocalOrMockAdapters(tmp_path: Path) -> None:
    session = MagicMock()
    clients = {name: MagicMock(name=name) for name in ("s3", "transcribe", "bedrock-runtime")}
    session.client.side_effect = lambda name, **_kwargs: clients[name]
    runtime = createProductionRuntime(executableEnvironment(tmp_path), boto3Session=session)
    assert isinstance(runtime.storage, S3StorageAdapter)
    assert isinstance(runtime.transcriber, AmazonTranscribeService)
    assert isinstance(runtime.observer, BedrockObserver)
    assert runtime.storage._client is clients["s3"]
    assert runtime.transcriber.transcribeClient is clients["transcribe"]
