import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
import shutil
import sys
from typing import Any, Callable, Dict, Mapping, Optional

from .audioDetector import AudioDetector
from .bedrockObserver import BedrockObserver
from .pipeline import processAssetManifest
from .storage import S3StorageAdapter
from .transcriber import (
    AmazonTranscribeService,
    TranscriptionPendingError
)


@dataclass(frozen=True)
class ProductionConfig:
    region: str
    mediaBucket: str
    transcribeOutputBucket: str
    bedrockModelId: str
    ffmpegPath: str
    ffprobePath: str

    @classmethod
    def fromEnvironment(
        cls,
        environment: Optional[Mapping[str, str]] = None
    ) -> "ProductionConfig":
        env = environment if environment is not None else os.environ
        required = (
            "AWS_REGION",
            "S3_MEDIA_BUCKET",
            "TRANSCRIBE_OUTPUT_BUCKET",
            "BEDROCK_OBSERVER_MODEL_ID",
            "FFMPEG_PATH",
            "FFPROBE_PATH"
        )
        missing = [name for name in required if not env.get(name)]
        if missing:
            raise RuntimeError(
                f"Missing required production configuration: {', '.join(sorted(missing))}"
            )

        ffmpegPath = cls._resolveBinary(env["FFMPEG_PATH"], "FFmpeg")
        ffprobePath = cls._resolveBinary(env["FFPROBE_PATH"], "ffprobe")
        return cls(
            region=env["AWS_REGION"],
            mediaBucket=env["S3_MEDIA_BUCKET"],
            transcribeOutputBucket=env["TRANSCRIBE_OUTPUT_BUCKET"],
            bedrockModelId=env["BEDROCK_OBSERVER_MODEL_ID"],
            ffmpegPath=ffmpegPath,
            ffprobePath=ffprobePath
        )

    @staticmethod
    def _resolveBinary(value: str, label: str) -> str:
        candidate = Path(value)
        if candidate.is_file():
            return str(candidate.resolve())
        resolved = shutil.which(value)
        if resolved:
            return resolved
        raise RuntimeError(f"Required {label} binary is unavailable: {value}")


@dataclass
class ProductionRuntime:
    skillId: str
    storage: S3StorageAdapter
    transcriber: AmazonTranscribeService
    observer: BedrockObserver
    audioDetector: AudioDetector

    def processManifest(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        if manifest.get("skillId") != self.skillId:
            raise ValueError("Manifest skillId does not match the scoped production runtime")
        return processAssetManifest(
            manifest,
            storageAdapter=self.storage,
            observer=self.observer,
            transcriber=self.transcriber,
            audioDetector=self.audioDetector
        )


def buildProductionRuntime(
    skillId: str,
    config: Optional[ProductionConfig] = None,
    sessionFactory: Optional[Callable[..., Any]] = None
) -> ProductionRuntime:
    if not skillId:
        raise ValueError("skillId is required")
    config = config or ProductionConfig.fromEnvironment()
    if sessionFactory is None:
        import boto3
        sessionFactory = boto3.Session
    session = sessionFactory(region_name=config.region)
    s3Client = session.client("s3")
    return ProductionRuntime(
        skillId=skillId,
        storage=S3StorageAdapter(
            config.mediaBucket,
            s3Client=s3Client,
            allowedPrefix=f"skills/{skillId}"
        ),
        transcriber=AmazonTranscribeService(
            transcribeClient=session.client("transcribe"),
            s3Client=s3Client,
            sourceBucket=config.mediaBucket,
            outputBucket=config.transcribeOutputBucket,
            regionName=config.region
        ),
        observer=BedrockObserver(
            bedrockClient=session.client("bedrock-runtime"),
            modelId=config.bedrockModelId
        ),
        audioDetector=AudioDetector(
            ffmpegPath=config.ffmpegPath,
            ffprobePath=config.ffprobePath
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="SkillTwin production media worker")
    parser.add_argument(
        "--manifest-key",
        required=True,
        help="Server-issued S3 key for the validated asset manifest"
    )
    args = parser.parse_args()

    config = ProductionConfig.fromEnvironment()
    import boto3
    session = boto3.Session(region_name=config.region)
    bootstrapStorage = S3StorageAdapter(
        config.mediaBucket,
        s3Client=session.client("s3")
    )
    manifest = json.loads(bootstrapStorage.readAsset(args.manifest_key))
    skillId = manifest.get("skillId")
    expectedPrefix = f"skills/{skillId}/" if skillId else ""
    if not expectedPrefix or not args.manifest_key.startswith(expectedPrefix):
        raise ValueError("Manifest key is not owned by its declared skillId")

    runtime = buildProductionRuntime(skillId, config, sessionFactory=lambda **_kwargs: session)
    try:
        result = runtime.processManifest(manifest)
    except TranscriptionPendingError as pending:
        print(json.dumps({
            "status": pending.state.value,
            "jobName": pending.jobName,
            "skillId": skillId
        }))
        sys.exit(75)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
