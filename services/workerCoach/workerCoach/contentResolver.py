import json
from pathlib import Path
from typing import Any, Dict, Optional

class ContentResolver:
    def resolveApprovedStep(self, stepId: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError("Subclasses must implement resolveApprovedStep")

    def resolveImageBytes(self, imageKey: str) -> bytes:
        raise NotImplementedError("Subclasses must implement resolveImageBytes")

class LocalContentResolver(ContentResolver):
    """
    Resolves step criteria and image bytes from local disk and contract fixtures.
    """

    def __init__(self, fixturesDir: Optional[Path] = None) -> None:
        if fixturesDir is not None:
            self.fixturesDir = fixturesDir
        else:
            current = Path(__file__).resolve().parent
            self.fixturesDir = current.parent.parent.parent / "packages" / "contracts" / "fixtures"

    def resolveApprovedStep(self, stepId: str) -> Optional[Dict[str, Any]]:
        pkgPath = self.fixturesDir / "skillPackage.valid.json"
        if not pkgPath.is_file():
            return None
        with open(pkgPath, "r", encoding="utf-8") as f:
            pkg = json.load(f)
        for step in pkg.get("steps", []):
            if step.get("stepId") == stepId:
                return step
        return None

    def resolveImageBytes(self, imageKey: str) -> bytes:
        localPath = Path(imageKey)
        if localPath.is_file():
            return localPath.read_bytes()
        # Simulated valid image byte payload when storage key is symbolic
        return b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"mock-image-content"
