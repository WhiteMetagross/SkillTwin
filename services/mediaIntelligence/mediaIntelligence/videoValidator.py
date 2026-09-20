from pathlib import Path
from typing import Any, Dict
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

    def toDict(self) -> Dict[str, Any]:
        return {
            "videoId": self.videoId,
            "sourceKey": self.sourceKey,
            "mimeType": self.mimeType,
            "durationMs": self.durationMs,
            "frameCount": self.frameCount,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
        }

class VideoValidator:
    """
    Validates video inputs according to SkillTwin contract specifications and media limits.
    Enforces the first release duration ceiling of 180 seconds per video.
    Rejects empty, corrupt, unreachable, or unsupported video formats.
    """

    MAX_DURATION_MS = 180000
    MAX_FILE_BYTES = 250 * 1024 * 1024
    MAX_WIDTH = 4096
    MAX_HEIGHT = 2160
    MAX_PIXELS = MAX_WIDTH * MAX_HEIGHT
    MAX_FPS = 120.0
    MAX_FRAME_COUNT = int((MAX_DURATION_MS / 1000) * MAX_FPS)
    SUPPORTED_MIME_TYPES = {
        "video/mp4",
        "video/webm",
        "video/quicktime"
    }
    MIME_EXTENSIONS = {
        "video/mp4": {".mp4", ".m4v"},
        "video/webm": {".webm"},
        "video/quicktime": {".mov"},
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
        suffix = Path(sourceKey).suffix.lower()
        if suffix not in self.MIME_EXTENSIONS[mimeType]:
            raise ValueError(
                f"Video {videoId} key extension '{suffix}' does not match media type '{mimeType}'"
            )

        if not localFilePath.is_file():
            raise FileNotFoundError(f"Video file unreachable at path: {localFilePath}")

        fileSize = localFilePath.stat().st_size
        if fileSize < 32:
            raise ValueError(f"Video file is empty or corrupted: {localFilePath}")
        if fileSize > self.MAX_FILE_BYTES:
            raise ValueError(
                f"Video {videoId} size of {fileSize} bytes exceeds limit of {self.MAX_FILE_BYTES} bytes"
            )

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

            if fps <= 0.0 or fps > self.MAX_FPS:
                raise ValueError(f"Video {videoId} has invalid or excessive frame rate: {fps}")
            if frameCount <= 0 or frameCount > self.MAX_FRAME_COUNT:
                raise ValueError(f"Video {videoId} has invalid or excessive frame count: {frameCount}")
            if width <= 0 or height <= 0:
                raise ValueError(f"Video {videoId} has invalid dimensions: {width}x{height}")
            if width > self.MAX_WIDTH or height > self.MAX_HEIGHT or width * height > self.MAX_PIXELS:
                raise ValueError(
                    f"Video {videoId} dimensions {width}x{height} exceed processing bounds"
                )

            durationMs = int((frameCount / fps) * 1000)

            if durationMs > self.MAX_DURATION_MS:
                raise ValueError(
                    f"Video {videoId} duration of {durationMs}ms exceeds maximum release limit of {self.MAX_DURATION_MS}ms"
                )
            if durationMs <= 0:
                raise ValueError(f"Video {videoId} has invalid duration: {durationMs}ms")

            # Decode bounded positions across the clip, not only its first frame.
            for positionMs in {durationMs // 2, max(0, durationMs - 100)}:
                cap.set(cv2.CAP_PROP_POS_MSEC, float(positionMs))
                positionDecoded, positionFrame = cap.read()
                if not positionDecoded or positionFrame is None:
                    raise ValueError(
                        f"Video stream cannot be decoded near {positionMs}ms: {localFilePath}"
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
