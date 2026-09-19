from pathlib import Path
from typing import Any, Dict, Optional
import cv2

class VideoMetadata:
    def __init__(
        self,
        videoId: str,
        sourceKey: str,
        mimeType: str,
        durationMs: int,
        frameCount: int,
        fps: float,
        width: int,
        height: int
    ) -> None:
        self.videoId = videoId
        self.sourceKey = sourceKey
        self.mimeType = mimeType
        self.durationMs = durationMs
        self.frameCount = frameCount
        self.fps = fps
        self.width = width
        self.height = height

class VideoValidator:
    """
    Validates video inputs according to SkillTwin contract specifications and media limits.
    Enforces the first release duration ceiling of 180 seconds per video.
    Rejects empty, corrupt, unreachable, or unsupported video formats.
    """

    MAX_DURATION_MS = 180000
    SUPPORTED_MIME_TYPES = {
        "video/mp4",
        "video/webm",
        "video/quicktime",
        "video/x-msvideo"
    }

    def validateVideoRecord(self, videoRecord: Dict[str, Any], localFilePath: Path) -> VideoMetadata:
        videoId = videoRecord.get("videoId", "")
        sourceKey = videoRecord.get("sourceKey", "")
        mimeType = videoRecord.get("mimeType", "")

        if not videoId:
            raise ValueError("Missing videoId in manifest video record")
        if not sourceKey:
            raise ValueError(f"Missing sourceKey for video {videoId}")

        if mimeType not in self.SUPPORTED_MIME_TYPES:
            raise ValueError(f"Unsupported media type '{mimeType}' for video {videoId}")

        if not localFilePath.is_file():
            raise FileNotFoundError(f"Video file unreachable at path: {localFilePath}")

        fileSize = localFilePath.stat().st_size
        if fileSize < 32:
            raise ValueError(f"Video file is empty or corrupted: {localFilePath}")

        # Verify decodability with OpenCV
        cap = cv2.VideoCapture(str(localFilePath))
        if not cap.isOpened():
            raise ValueError(f"Video file could not be opened or decoded: {localFilePath}")

        try:
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            frameCount = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

            # Read first frame to ensure decoder can genuinely decode video frames
            grabbed, testFrame = cap.read()
            if not grabbed or testFrame is None:
                raise ValueError(f"Video stream cannot be decoded or has zero valid frames: {localFilePath}")

            if fps <= 0.0:
                fps = 25.0
            if frameCount <= 0:
                frameCount = 1

            durationMs = int((frameCount / fps) * 1000)

            if durationMs > self.MAX_DURATION_MS:
                raise ValueError(
                    f"Video {videoId} duration of {durationMs}ms exceeds maximum release limit of {self.MAX_DURATION_MS}ms"
                )

            return VideoMetadata(
                videoId=videoId,
                sourceKey=sourceKey,
                mimeType=mimeType,
                durationMs=durationMs,
                frameCount=frameCount,
                fps=fps,
                width=width,
                height=height
            )
        finally:
            cap.release()
