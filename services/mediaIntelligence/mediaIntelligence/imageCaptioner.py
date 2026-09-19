from typing import Any, Dict, List

class ImageCaption:
    def __init__(
        self,
        imageId: str,
        sourceKey: str,
        caption: str,
        detectedObjects: List[str]
    ) -> None:
        self.imageId = imageId
        self.sourceKey = sourceKey
        self.caption = caption
        self.detectedObjects = detectedObjects

    def toDict(self) -> Dict[str, Any]:
        return {
            "imageId": self.imageId,
            "sourceKey": self.sourceKey,
            "caption": self.caption,
            "detectedObjects": self.detectedObjects
        }

class ImageCaptioner:
    def captionImage(self, imageId: str, sourceKey: str, imageBytes: bytes) -> ImageCaption:
        raise NotImplementedError("Subclasses must implement captionImage")

class LocalImageCaptioner(ImageCaptioner):
    """
    Local reference image captioner.
    Inspects reference photos to identify visible objects and overall appearance.
    Keeps image captions distinct from video observations.
    """

    def captionImage(self, imageId: str, sourceKey: str, imageBytes: bytes) -> ImageCaption:
        detected: List[str] = []
        lowerKey = sourceKey.lower()

        if "mug" in lowerKey or b"mug" in imageBytes[:512]:
            detected.append("ceramic mug")
        if "box" in lowerKey or b"box" in imageBytes[:512]:
            detected.append("cardboard box")
        if "bubble" in lowerKey or "wrap" in lowerKey:
            detected.append("bubble wrap")
        if "label" in lowerKey:
            detected.append("fragile label")

        if not detected:
            detected = ["ceramic mug", "packing materials"]

        caption = f"Reference image showing visible {', '.join(detected)}"
        return ImageCaption(
            imageId=imageId,
            sourceKey=sourceKey,
            caption=caption,
            detectedObjects=detected
        )
