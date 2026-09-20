from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set

from PIL import Image

from .audioDetector import AudioDetector
from .bundleComposer import BundleComposer
from .imageCaptioner import ImageCaption, ImageCaptioner, LocalImageCaptioner
from .observer import LocalMediaObserver, MediaObserver, Observation
from .storage import (
    LocalStorageAdapter,
    StorageAdapter,
    validateOwnedSourceKey,
)
from .transcriber import LocalTranscribeService, TranscribeService, TranscriptSegment
from .validator import validateSchema
from .videoSampler import SampledFrame, VideoSampler
from .videoValidator import VideoMetadata, VideoValidator


MAX_REFERENCE_IMAGE_BYTES = 10 * 1024 * 1024
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_IMAGE_PIXELS = 32_000_000
SUPPORTED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
SUPPORTED_DOCUMENT_MIME_TYPES = {"application/pdf"}


def _validateObjectMetadata(
    storage: StorageAdapter,
    key: str,
    declaredMimeType: str,
    maxBytes: int,
) -> None:
    metadata = storage.getObjectMetadata(key)
    if metadata.contentLength <= 0:
        raise ValueError(f"Asset '{key}' is empty")
    if metadata.contentLength > maxBytes:
        raise ValueError(
            f"Asset '{key}' size {metadata.contentLength} bytes exceeds {maxBytes} byte limit"
        )
    if metadata.contentType:
        actualMime = metadata.contentType.split(";", 1)[0].strip().lower()
        if actualMime != declaredMimeType.lower():
            raise ValueError(
                f"Asset '{key}' content type '{actualMime}' does not match manifest '{declaredMimeType}'"
            )


def _validateReferenceImage(imageId: str, imageBytes: bytes) -> None:
    import io
    try:
        image = Image.open(io.BytesIO(imageBytes))
    except Exception as exc:
        raise ValueError(f"Reference image '{imageId}' is corrupt or undecodable") from exc
    with image:
        width, height = image.size
        if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
            raise ValueError(
                f"Reference image '{imageId}' dimensions {width}x{height} exceed bounds"
            )
        try:
            image.verify()
        except Exception as exc:
            raise ValueError(f"Reference image '{imageId}' is corrupt or undecodable") from exc


def processAssetManifest(
    manifest: Dict[str, Any],
    assetRoot: Optional[Path] = None,
    storageAdapter: Optional[StorageAdapter] = None,
    observer: Optional[MediaObserver] = None,
    transcriber: Optional[TranscribeService] = None,
    audioDetector: Optional[AudioDetector] = None,
    videoValidator: Optional[VideoValidator] = None,
    videoSampler: Optional[VideoSampler] = None,
    imageCaptioner: Optional[ImageCaptioner] = None,
    enforceOwnedKeys: bool = False,
    validateAllManifestAssets: bool = False,
) -> Dict[str, Any]:
    """Validate, stage, inspect, and compose one contract-compatible evidence bundle."""
    validManifest, manifestError = validateSchema("assetManifest", manifest)
    if not validManifest:
        raise ValueError(f"Invalid asset manifest: {manifestError}")

    videos = manifest.get("videos", [])
    if not (1 <= len(videos) <= 3):
        raise ValueError(f"Manifest must contain between 1 and 3 videos, found {len(videos)}")

    skillId = manifest["skillId"]
    storage = storageAdapter or LocalStorageAdapter(assetRoot)
    validator = videoValidator or VideoValidator()
    sampler = videoSampler or VideoSampler(intervalMs=1500)
    detector = audioDetector or AudioDetector()
    transcribeSvc = transcriber or LocalTranscribeService()
    captioner = imageCaptioner or LocalImageCaptioner()
    mediaObserver = observer or LocalMediaObserver()
    composer = BundleComposer()

    videoRecords: List[Dict[str, Any]] = []
    perVideoObservations: Dict[str, List[Observation]] = {}
    videoDurationMap: Dict[str, int] = {}
    suppliedFrameKeysMap: Dict[str, Set[str]] = {}
    validatedVideos: List[tuple[Dict[str, Any], VideoMetadata, Path]] = []

    try:
        # Validate every manifest key before frame extraction or provider/model calls.
        for video in videos:
            sourceKey = video["sourceKey"]
            if enforceOwnedKeys and not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._-]*", video["videoId"],
            ):
                raise ValueError(f"Invalid production videoId: {video['videoId']}")
            if video["mimeType"] not in validator.SUPPORTED_MIME_TYPES:
                raise ValueError(
                    f"Unsupported media type '{video['mimeType']}' for video {video['videoId']}"
                )
            if enforceOwnedKeys:
                validateOwnedSourceKey(skillId, sourceKey, "videos")
            _validateObjectMetadata(storage, sourceKey, video["mimeType"], validator.MAX_FILE_BYTES)
            localPath = storage.resolveLocalPath(sourceKey)
            if localPath is None or not localPath.is_file():
                raise FileNotFoundError(
                    f"Video file for videoId '{video['videoId']}' not found at key: {sourceKey}"
                )
            metadata = validator.validateVideoRecord(video, localPath)
            validatedVideos.append((video, metadata, localPath))
            videoDurationMap[video["videoId"]] = metadata.durationMs

        referenceCaptions: List[ImageCaption] = []
        for reference in manifest.get("referenceImages", []):
            key = reference["sourceKey"]
            mimeType = reference["mimeType"]
            if mimeType not in SUPPORTED_IMAGE_MIME_TYPES:
                raise ValueError(f"Unsupported reference image MIME type: {mimeType}")
            if enforceOwnedKeys:
                validateOwnedSourceKey(skillId, key, "images")
            if validateAllManifestAssets or storage.assetExists(key):
                _validateObjectMetadata(storage, key, mimeType, MAX_REFERENCE_IMAGE_BYTES)
                imageBytes = storage.readAsset(key, maxBytes=MAX_REFERENCE_IMAGE_BYTES)
                _validateReferenceImage(reference["imageId"], imageBytes)
                referenceCaptions.append(
                    captioner.captionImage(reference["imageId"], key, imageBytes)
                )

        for document in manifest.get("documents", []):
            key = document["sourceKey"]
            mimeType = document["mimeType"]
            if mimeType not in SUPPORTED_DOCUMENT_MIME_TYPES:
                raise ValueError(f"Unsupported document MIME type: {mimeType}")
            if enforceOwnedKeys:
                validateOwnedSourceKey(skillId, key, "documents")
            if validateAllManifestAssets or storage.assetExists(key):
                _validateObjectMetadata(storage, key, mimeType, MAX_DOCUMENT_BYTES)

        for video, metadata, localPath in validatedVideos:
            videoId = video["videoId"]
            sourceKey = video["sourceKey"]

            frames: List[SampledFrame] = sampler.sampleFrames(
                metadata, localPath, skillId, storage,
            )
            suppliedFrameKeysMap[videoId] = {frame.storageKey for frame in frames}

            audioResult = detector.inspectAudio(localPath)
            segments: List[TranscriptSegment] = []
            if audioResult.hasUsableSpeech:
                transcription = transcribeSvc.transcribe(
                    videoId=videoId,
                    skillId=skillId,
                    localFilePath=localPath,
                    storageAdapter=storage,
                    sourceKey=sourceKey,
                    sourceLanguage=manifest["sourceLanguage"],
                )
                segments = transcription.segments
                videoRecords.append({
                    "videoId": videoId,
                    "hasNarration": transcription.hasNarration,
                    "transcriptKey": transcription.transcriptKey,
                })
            else:
                videoRecords.append({
                    "videoId": videoId,
                    "hasNarration": False,
                    "transcriptKey": None,
                })

            observations = mediaObserver.observeVideo(
                videoId=videoId,
                skillId=skillId,
                frames=frames,
                transcriptSegments=segments,
                referenceCaptions=referenceCaptions,
            )
            if not observations:
                raise ValueError(
                    f"Video '{videoId}' could not be analyzed: "
                    "no recognizable packaging actions or objects observed"
                )
            perVideoObservations[videoId] = observations

        return composer.composeBundle(
            skillId=skillId,
            videoRecords=videoRecords,
            perVideoObservations=perVideoObservations,
            storageAdapter=storage,
            videoDurationMap=videoDurationMap,
            suppliedFrameKeysMap=suppliedFrameKeysMap,
        )
    finally:
        storage.cleanup()
