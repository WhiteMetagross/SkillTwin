from dataclasses import dataclass
import os
from pathlib import Path
import shutil
from typing import Any, Dict, Mapping, Optional

from .audioDetector import AudioDetector
from .bedrockObserver import BedrockObserver
from .errors import RuntimeConfigurationError
from .imageCaptioner import ValidatedImageCaptioner
from .pipeline import processAssetManifest
from .storage import S3StorageAdapter
from .transcriber import AmazonTranscribeService
from .transcriber import TranscriptionJobIdentity, TranscriptionResult, TranscriptionStatus
from .videoSampler import VideoSampler
from .videoValidator import VideoValidator


@dataclass(frozen=True)
class ProductionConfig:
    awsRegion: str
    mediaBucket: str
    transcribeOutputBucket: str
    observerModelId: str
    ffmpegPath: str
    ffprobePath: str
    maxObjectBytes: int
    maxStagingBytes: int
    frameSampleIntervalMs: int
    maxFrames: int

    @classmethod
    def fromEnvironment(
        cls, environment: Optional[Mapping[str, str]] = None,
    ) -> "ProductionConfig":
        env = dict(os.environ if environment is None else environment)
        required = {
            "AWS_REGION": env.get("AWS_REGION", "").strip(),
            "S3_MEDIA_BUCKET": env.get("S3_MEDIA_BUCKET", "").strip(),
            "BEDROCK_OBSERVER_MODEL_ID": env.get("BEDROCK_OBSERVER_MODEL_ID", "").strip(),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeConfigurationError(
                "Missing required production configuration: " + ", ".join(sorted(missing))
            )

        ffmpegPath = env.get("FFMPEG_PATH", "").strip() or shutil.which("ffmpeg") or ""
        ffprobePath = env.get("FFPROBE_PATH", "").strip() or shutil.which("ffprobe") or ""
        binaryErrors = []
        if not ffmpegPath or not Path(ffmpegPath).is_file():
            binaryErrors.append("ffmpeg (set FFMPEG_PATH)")
        if not ffprobePath or not Path(ffprobePath).is_file():
            binaryErrors.append("ffprobe (set FFPROBE_PATH)")
        if binaryErrors:
            raise RuntimeConfigurationError(
                "Missing required production media binaries: " + ", ".join(binaryErrors)
            )

        def positiveInt(name: str, default: int) -> int:
            raw = env.get(name, str(default)).strip()
            try:
                value = int(raw)
            except ValueError as exc:
                raise RuntimeConfigurationError(f"{name} must be an integer, received '{raw}'") from exc
            if value <= 0:
                raise RuntimeConfigurationError(f"{name} must be positive")
            return value

        maxObjectBytes = positiveInt("MEDIA_MAX_OBJECT_BYTES", VideoValidator.MAX_FILE_BYTES)
        if maxObjectBytes > VideoValidator.MAX_FILE_BYTES:
            raise RuntimeConfigurationError(
                f"MEDIA_MAX_OBJECT_BYTES cannot exceed {VideoValidator.MAX_FILE_BYTES}"
            )
        maxFrames = positiveInt("MEDIA_MAX_FRAMES", VideoSampler.MAX_FRAMES)
        if maxFrames > VideoSampler.MAX_FRAMES:
            raise RuntimeConfigurationError(
                f"MEDIA_MAX_FRAMES cannot exceed {VideoSampler.MAX_FRAMES}"
            )
        frameSampleIntervalMs = positiveInt("FRAME_SAMPLE_INTERVAL_MS", 1500)
        if frameSampleIntervalMs < 500:
            raise RuntimeConfigurationError("FRAME_SAMPLE_INTERVAL_MS cannot be less than 500")

        return cls(
            awsRegion=required["AWS_REGION"],
            mediaBucket=required["S3_MEDIA_BUCKET"],
            transcribeOutputBucket=env.get("TRANSCRIBE_OUTPUT_BUCKET", "").strip()
            or required["S3_MEDIA_BUCKET"],
            observerModelId=required["BEDROCK_OBSERVER_MODEL_ID"],
            ffmpegPath=ffmpegPath,
            ffprobePath=ffprobePath,
            maxObjectBytes=maxObjectBytes,
            maxStagingBytes=positiveInt("MEDIA_MAX_STAGING_BYTES", 750 * 1024 * 1024),
            frameSampleIntervalMs=frameSampleIntervalMs,
            maxFrames=maxFrames,
        )


@dataclass
class ProductionMediaRuntime:
    config: ProductionConfig
    storage: S3StorageAdapter
    transcriber: AmazonTranscribeService
    observer: BedrockObserver
    audioDetector: AudioDetector
    videoValidator: VideoValidator
    videoSampler: VideoSampler

    def processManifest(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        return processAssetManifest(
            manifest,
            storageAdapter=self.storage,
            observer=self.observer,
            transcriber=self.transcriber,
            audioDetector=self.audioDetector,
            videoValidator=self.videoValidator,
            videoSampler=self.videoSampler,
            imageCaptioner=ValidatedImageCaptioner(),
            enforceOwnedKeys=True,
            validateAllManifestAssets=True,
        )

    def startTranscription(
        self,
        videoId: str,
        skillId: str,
        sourceKey: str,
        sourceLanguage: str,
        mediaFormat: str,
    ) -> TranscriptionJobIdentity:
        return self.transcriber.startTranscription(
            videoId, skillId, sourceKey, sourceLanguage, mediaFormat,
        )

    def getTranscriptionStatus(
        self, identity: TranscriptionJobIdentity,
    ) -> TranscriptionStatus:
        return self.transcriber.getTranscriptionStatus(identity)

    def completeTranscription(
        self, status: TranscriptionStatus,
    ) -> TranscriptionResult:
        return self.transcriber.completeTranscription(status, self.storage)


def createProductionRuntime(
    environment: Optional[Mapping[str, str]] = None,
    boto3Session: Optional[Any] = None,
) -> ProductionMediaRuntime:
    config = ProductionConfig.fromEnvironment(environment)
    if boto3Session is None:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeConfigurationError("boto3 is required in production mode") from exc
        boto3Session = boto3.session.Session(region_name=config.awsRegion)

    try:
        s3Client = boto3Session.client("s3", region_name=config.awsRegion)
        transcribeClient = boto3Session.client("transcribe", region_name=config.awsRegion)
        bedrockClient = boto3Session.client("bedrock-runtime", region_name=config.awsRegion)
    except Exception as exc:
        raise RuntimeConfigurationError(f"Failed to construct AWS production clients: {exc}") from exc

    storage = S3StorageAdapter(
        config.mediaBucket,
        s3Client=s3Client,
        maxObjectBytes=config.maxObjectBytes,
        maxStagingBytes=config.maxStagingBytes,
    )
    transcriber = AmazonTranscribeService(
        sourceBucket=config.mediaBucket,
        outputBucket=config.transcribeOutputBucket,
        transcribeClient=transcribeClient,
        s3Client=s3Client,
    )
    runtime = ProductionMediaRuntime(
        config=config,
        storage=storage,
        transcriber=transcriber,
        observer=BedrockObserver(bedrockClient=bedrockClient, modelId=config.observerModelId),
        audioDetector=AudioDetector(config.ffmpegPath, config.ffprobePath),
        videoValidator=VideoValidator(),
        videoSampler=VideoSampler(config.frameSampleIntervalMs, config.maxFrames),
    )
    # Defensive assertion: production construction must never drift to local/mock adapters.
    if not isinstance(runtime.storage, S3StorageAdapter):
        raise RuntimeConfigurationError("Production runtime did not construct S3 storage")
    if not isinstance(runtime.transcriber, AmazonTranscribeService):
        raise RuntimeConfigurationError("Production runtime did not construct Amazon Transcribe")
    if not isinstance(runtime.observer, BedrockObserver):
        raise RuntimeConfigurationError("Production runtime did not construct Bedrock observer")
    return runtime
