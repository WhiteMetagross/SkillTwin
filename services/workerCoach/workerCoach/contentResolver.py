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
    Resolves approved step criteria and image bytes from disk.
    Strictly verifies that skill packages are approved before resolving step criteria.
    Never fabricates image bytes for missing files.
    """

    def __init__(
        self,
        fixturesDir: Optional[Path] = None,
        approvedPackage: Optional[Dict[str, Any]] = None,
        sessionPackages: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> None:
        if fixturesDir is not None:
            self.fixturesDir = fixturesDir
        else:
            current = Path(__file__).resolve().parent
            self.fixturesDir = current.parent.parent.parent / "packages" / "contracts" / "fixtures"

        self.approvedPackage = approvedPackage
        self.sessionPackages = sessionPackages or {}

    def resolveApprovedStep(self, stepId: str, sessionId: Optional[str] = None) -> Optional[Dict[str, Any]]:
        # If session specified and package mapped
        if sessionId and sessionId in self.sessionPackages:
            pkg = self.sessionPackages[sessionId]
            if pkg.get("status") == "approved" and pkg.get("version", 0) > 0:
                for step in pkg.get("steps", []):
                    if step.get("stepId") == stepId:
                        return step
            return None

        # If explicit approved package provided
        if self.approvedPackage is not None:
            if self.approvedPackage.get("status") == "approved" and self.approvedPackage.get("version", 0) > 0:
                for step in self.approvedPackage.get("steps", []):
                    if step.get("stepId") == stepId:
                        return step
            return None

        # Check for approved package fixture
        approvedPkgPath = self.fixturesDir / "skillPackage.approved.valid.json"
        if approvedPkgPath.is_file():
            try:
                with open(approvedPkgPath, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
                if pkg.get("status") == "approved" and pkg.get("version", 0) > 0:
                    for step in pkg.get("steps", []):
                        if step.get("stepId") == stepId:
                            return step
            except Exception:
                return None

        # Standard fixture is rejected if not approved
        pkgPath = self.fixturesDir / "skillPackage.valid.json"
        if pkgPath.is_file():
            try:
                with open(pkgPath, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
                if pkg.get("status") == "approved" and pkg.get("version", 0) > 0:
                    for step in pkg.get("steps", []):
                        if step.get("stepId") == stepId:
                            return step
            except Exception:
                return None

        return None

    def resolveImageBytes(self, imageKey: str) -> bytes:
        if not imageKey:
            return b""
        localPath = Path(imageKey)
        if localPath.is_file():
            return localPath.read_bytes()
        # Never fabricate fake JPEG bytes for nonexistent files
        return b""
