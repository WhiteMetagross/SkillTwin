from pathlib import Path
from typing import Any, Dict, List, Optional
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
    transcriber: Optional[TranscribeService] = None
) -> Dict[str, Any]:
    """
    Narrow service entry point for SkillTwin media intelligence pipeline.
    Validates manifest, inspects independent videos, detects usable speech,
    samples frames to storage, observes visual actions, and composes a validated evidence bundle.
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
    audioDetector = AudioDetector()
    transcribeSvc = transcriber or LocalTranscribeService()
    captioner = LocalImageCaptioner()
    mediaObserver = observer or LocalMediaObserver()
    composer = BundleComposer()

    # Process reference images if present
    referenceCaptions: List[ImageCaption] = []
    for ref in manifest.get("referenceImages", []):
        refKey = ref.get("sourceKey", "")
        refId = ref.get("imageId", "")
        if refKey and storage.assetExists(refKey):
            refBytes = storage.readAsset(refKey)
            caption = captioner.captionImage(refId, refKey, refBytes)
            referenceCaptions.append(caption)

    videoRecords: List[Dict[str, Any]] = []
    perVideoObservations: Dict[str, List[Observation]] = {}

    for vRecord in videos:
        videoId = vRecord["videoId"]
        sourceKey = vRecord["sourceKey"]

        localPath = storage.resolveLocalPath(sourceKey)
        if localPath is None or not localPath.is_file():
            raise FileNotFoundError(f"Video file for videoId '{videoId}' not found at key: {sourceKey}")

        # Validate video decodability and duration limit
        metadata = videoValidator.validateVideoRecord(vRecord, localPath)

        # Sample frames and store JPEG artifacts
        frames: List[SampledFrame] = sampler.sampleFrames(metadata, localPath, skillId, storage)

        # Inspect audio for usable speech
        audioResult = audioDetector.inspectAudio(localPath)

        if audioResult.hasUsableSpeech:
            transcriptKey = transcribeSvc.transcribeVideo(
                videoId=videoId,
                skillId=skillId,
                localFilePath=localPath,
                storageAdapter=storage,
                knownSegments=audioResult.speechSegments
            )
            segments: List[TranscriptSegment] = [
                TranscriptSegment(
                    startMs=s.get("startMs", 0),
                    endMs=s.get("endMs", 0),
                    text=s.get("text", ""),
                    confidence=s.get("confidence", 0.95)
                )
                for s in audioResult.speechSegments
            ]
            videoRecords.append({
                "videoId": videoId,
                "hasNarration": True,
                "transcriptKey": transcriptKey
            })
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
        perVideoObservations[videoId] = obsList

    return composer.composeBundle(
        skillId=skillId,
        videoRecords=videoRecords,
        perVideoObservations=perVideoObservations,
        storageAdapter=storage
    )
