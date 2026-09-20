from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from .audioDetector import AudioDetector
from .bundleComposer import BundleComposer
from .imageCaptioner import ImageCaption, LocalImageCaptioner
from .observer import LocalMediaObserver, MediaObserver, Observation
from .storage import LocalStorageAdapter, StorageAdapter
from .transcriber import LocalTranscribeService, TranscribeService, TranscriptSegment
from .validator import validateSchema
from .videoSampler import SampledFrame, VideoSampler
from .videoValidator import VideoValidator

def processAssetManifest(
    manifest: Dict[str, Any],
    assetRoot: Optional[Path] = None,
    storageAdapter: Optional[StorageAdapter] = None,
    observer: Optional[MediaObserver] = None,
    transcriber: Optional[TranscribeService] = None,
    audioDetector: Optional[AudioDetector] = None
) -> Dict[str, Any]:
    """
    Narrow service entry point for SkillTwin media intelligence pipeline.
    Validates manifest, inspects independent videos, detects usable speech,
    samples frames to storage, observes visual actions, and composes a validated evidence bundle.
    Staged remote media files are safely cleaned up upon completion.
    """
    validManifest, manifestError = validateSchema("assetManifest", manifest)
    if not validManifest:
        raise ValueError(f"Invalid asset manifest: {manifestError}")

    videos = manifest.get("videos", [])
    if not (1 <= len(videos) <= 3):
        raise ValueError(f"Manifest must contain between 1 and 3 videos, found {len(videos)}")

    skillId = manifest["skillId"]
    storage = storageAdapter or LocalStorageAdapter(assetRoot)
    videoValidator = VideoValidator()
    sampler = VideoSampler(intervalMs=1500)
    audioInspector = audioDetector or AudioDetector()
    transcribeSvc = transcriber or LocalTranscribeService()
    captioner = LocalImageCaptioner()
    mediaObserver = observer or LocalMediaObserver()
    composer = BundleComposer()

    videoRecords: List[Dict[str, Any]] = []
    perVideoObservations: Dict[str, List[Observation]] = {}
    videoDurationMap: Dict[str, int] = {}
    suppliedFrameKeysMap: Dict[str, Set[str]] = {}

    try:
        # Process reference images if present
        referenceCaptions: List[ImageCaption] = []
        for ref in manifest.get("referenceImages", []):
            refKey = ref.get("sourceKey", "")
            refId = ref.get("imageId", "")
            if refKey and storage.assetExists(refKey):
                refBytes = storage.readAsset(refKey)
                caption = captioner.captionImage(refId, refKey, refBytes)
                referenceCaptions.append(caption)

        for vRecord in videos:
            videoId = vRecord["videoId"]
            sourceKey = vRecord["sourceKey"]

            localPath = storage.resolveLocalPath(sourceKey)
            if localPath is None or not localPath.is_file():
                raise FileNotFoundError(f"Video file for videoId '{videoId}' not found at key: {sourceKey}")

            # Validate video decodability and duration limit
            metadata = videoValidator.validateVideoRecord(vRecord, localPath)
            videoDurationMap[videoId] = metadata.durationMs

            # Sample frames and store JPEG artifacts
            frames: List[SampledFrame] = sampler.sampleFrames(metadata, localPath, skillId, storage)
            suppliedKeys = {f.storageKey for f in frames}
            suppliedFrameKeysMap[videoId] = suppliedKeys

            # Inspect actual audio stream for acoustic speech characteristics
            audioResult = audioInspector.inspectAudio(localPath)

            if audioResult.hasUsableSpeech:
                transcriptKey, segments = transcribeSvc.transcribe(
                    videoId=videoId,
                    skillId=skillId,
                    localFilePath=localPath,
                    storageAdapter=storage,
                    sourceKey=sourceKey,
                    sourceLanguage=manifest.get("sourceLanguage", "auto")
                )
                if transcriptKey is not None and storage.assetExists(transcriptKey):
                    videoRecords.append({
                        "videoId": videoId,
                        "hasNarration": True,
                        "transcriptKey": transcriptKey
                    })
                else:
                    videoRecords.append({
                        "videoId": videoId,
                        "hasNarration": False,
                        "transcriptKey": None
                    })
                    segments = []
            else:
                segments = []
                videoRecords.append({
                    "videoId": videoId,
                    "hasNarration": False,
                    "transcriptKey": None
                })

            # Observe frames and aligned transcript segments
            obsList = mediaObserver.observeVideo(
                videoId=videoId,
                skillId=skillId,
                frames=frames,
                transcriptSegments=segments,
                referenceCaptions=referenceCaptions
            )
            if not obsList:
                raise ValueError(
                    f"Video '{videoId}' could not be analyzed: no recognizable packaging actions or objects observed"
                )

            perVideoObservations[videoId] = obsList

        return composer.composeBundle(
            skillId=skillId,
            videoRecords=videoRecords,
            perVideoObservations=perVideoObservations,
            storageAdapter=storage,
            videoDurationMap=videoDurationMap,
            suppliedFrameKeysMap=suppliedFrameKeysMap
        )
    finally:
        storage.cleanup()
