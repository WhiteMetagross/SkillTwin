import math
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

class VideoSampler:
    """
    Samples video frames at configured intervals of roughly one to two seconds.
    Writes representative JPEG image artifacts to storage using standardized keys.
    """

    MAX_FRAMES = 120
    MAX_WIDTH = 1920
    MAX_HEIGHT = 1080
    MAX_JPEG_BYTES = 2 * 1024 * 1024
    MAX_TOTAL_FRAME_BYTES = 64 * 1024 * 1024

    def __init__(self, intervalMs: int = 1500) -> None:
        self.intervalMs = min(max(500, intervalMs), 3000)

    def targetTimestamps(self, durationMs: int) -> List[int]:
        if durationMs <= 0:
            raise ValueError("Video duration must be positive")
        boundedInterval = max(
            self.intervalMs,
            math.ceil(durationMs / self.MAX_FRAMES)
        )
        timestamps = list(range(0, durationMs, boundedInterval))
        if len(timestamps) > self.MAX_FRAMES:
            raise ValueError("Frame sampling plan exceeds maximum frame count")
        return timestamps

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
        totalFrameBytes = 0

        try:
            for currentTs in self.targetTimestamps(totalDurationMs):
                frameIdx = int((currentTs / 1000.0) * fps)
                cap.set(cv2.CAP_PROP_POS_MSEC, float(currentTs))
                success, frame = cap.read()

                if not success or frame is None:
                    raise ValueError(
                        f"Video sampling failed at {currentTs}ms; full coverage is unavailable"
                    )

                height, width = frame.shape[:2]
                scale = min(
                    1.0,
                    self.MAX_WIDTH / max(width, 1),
                    self.MAX_HEIGHT / max(height, 1)
                )
                if scale < 1.0:
                    width = max(1, int(width * scale))
                    height = max(1, int(height * scale))
                    frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)

                qualityParams = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
                encodedOk, buffer = cv2.imencode(".jpg", frame, qualityParams)
                if not encodedOk:
                    raise ValueError(f"Could not encode sampled frame at {currentTs}ms")

                jpegBytes = buffer.tobytes()
                if len(jpegBytes) > self.MAX_JPEG_BYTES:
                    raise ValueError(f"Sampled frame at {currentTs}ms exceeds JPEG byte limit")
                totalFrameBytes += len(jpegBytes)
                if totalFrameBytes > self.MAX_TOTAL_FRAME_BYTES:
                    raise ValueError("Sampled frame artifacts exceed total byte limit")
                storageKey = f"skills/{skillId}/derived/frames/{videoId}/{currentTs}.jpg"
                storageAdapter.writeAsset(storageKey, jpegBytes)

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

        finally:
            cap.release()

        return frames
