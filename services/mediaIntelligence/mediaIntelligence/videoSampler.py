from pathlib import Path
from typing import List
import cv2
from .storage import StorageAdapter
from .videoValidator import VideoMetadata

class SampledFrame:
    def __init__(
        self,
        videoId: str,
        timestampMs: int,
        frameIndex: int,
        storageKey: str,
        imageBytes: bytes,
        width: int,
        height: int
    ) -> None:
        self.videoId = videoId
        self.timestampMs = timestampMs
        self.frameIndex = frameIndex
        self.storageKey = storageKey
        self.imageBytes = imageBytes
        self.width = width
        self.height = height

    def toManifestEntry(self) -> dict:
        return {
            "videoId": self.videoId,
            "timestampMs": self.timestampMs,
            "frameIndex": self.frameIndex,
            "storageKey": self.storageKey,
            "width": self.width,
            "height": self.height,
            "sizeBytes": len(self.imageBytes),
        }

class VideoSampler:
    """
    Samples video frames at configured intervals of roughly one to two seconds.
    Writes representative JPEG image artifacts to storage using standardized keys.
    """

    MAX_FRAMES = 120
    MAX_FRAME_BYTES = 4 * 1024 * 1024
    MAX_TOTAL_FRAME_BYTES = 64 * 1024 * 1024

    def __init__(self, intervalMs: int = 1500, maxFrames: int = MAX_FRAMES) -> None:
        self.intervalMs = max(500, intervalMs)
        if maxFrames <= 0 or maxFrames > self.MAX_FRAMES:
            raise ValueError(f"maxFrames must be between 1 and {self.MAX_FRAMES}")
        self.maxFrames = maxFrames

    def sampleFrames(
        self,
        metadata: VideoMetadata,
        localFilePath: Path,
        skillId: str,
        storageAdapter: StorageAdapter
    ) -> List[SampledFrame]:
        cap = cv2.VideoCapture(str(localFilePath))
        if not cap.isOpened():
            raise ValueError(f"Cannot open video for frame sampling: {localFilePath}")

        frames: List[SampledFrame] = []
        fps = metadata.fps if metadata.fps > 0 else 25.0
        totalDurationMs = metadata.durationMs
        videoId = metadata.videoId
        effectiveIntervalMs = max(
            self.intervalMs,
            (totalDurationMs + self.maxFrames - 1) // self.maxFrames,
        )
        totalFrameBytes = 0

        try:
            # Determine target timestamps spaced at intervalMs
            currentTs = 0
            while currentTs < totalDurationMs and len(frames) < self.maxFrames:
                frameIdx = int((currentTs / 1000.0) * fps)
                cap.set(cv2.CAP_PROP_POS_MSEC, float(currentTs))
                success, frame = cap.read()

                if not success or frame is None:
                    # If seek failed, try breaking
                    break

                # Encode frame as JPEG
                qualityParams = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
                encodedOk, buffer = cv2.imencode(".jpg", frame, qualityParams)
                if not encodedOk:
                    currentTs += effectiveIntervalMs
                    continue

                jpegBytes = buffer.tobytes()
                if len(jpegBytes) > self.MAX_FRAME_BYTES:
                    raise ValueError(
                        f"Sampled frame at {currentTs}ms exceeds {self.MAX_FRAME_BYTES} byte limit"
                    )
                totalFrameBytes += len(jpegBytes)
                if totalFrameBytes > self.MAX_TOTAL_FRAME_BYTES:
                    raise ValueError("Sampled frame set exceeds total in-memory work limit")
                storageKey = f"skills/{skillId}/derived/frames/{videoId}/{currentTs}.jpg"
                storageAdapter.writeAsset(storageKey, jpegBytes)

                height, width = frame.shape[:2]
                frames.append(
                    SampledFrame(
                        videoId=videoId,
                        timestampMs=currentTs,
                        frameIndex=frameIdx,
                        storageKey=storageKey,
                        imageBytes=jpegBytes,
                        width=width,
                        height=height
                    )
                )

                currentTs += effectiveIntervalMs

            # Ensure at least one frame was sampled
            if not frames:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                success, frame = cap.read()
                if success and frame is not None:
                    encodedOk, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                    if encodedOk:
                        jpegBytes = buffer.tobytes()
                        storageKey = f"skills/{skillId}/derived/frames/{videoId}/0.jpg"
                        storageAdapter.writeAsset(storageKey, jpegBytes)
                        height, width = frame.shape[:2]
                        frames.append(
                            SampledFrame(
                                videoId=videoId,
                                timestampMs=0,
                                frameIndex=0,
                                storageKey=storageKey,
                                imageBytes=jpegBytes,
                                width=width,
                                height=height
                            )
                        )
        finally:
            cap.release()

        return frames
