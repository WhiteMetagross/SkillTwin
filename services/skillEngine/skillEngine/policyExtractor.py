import io
from pathlib import Path
from typing import Any, Dict, List, Optional

class PolicySection:
    def __init__(self, documentId: str, page: int, section: str, text: str) -> None:
        self.documentId = documentId
        self.page = page
        self.section = section
        self.text = text

class PolicyDocument:
    def __init__(self, documentId: str, sections: List[PolicySection]) -> None:
        self.documentId = documentId
        self.sections = sections

class PolicyExtractor:
    def extractDocument(self, documentId: str, content: bytes) -> PolicyDocument:
        raise NotImplementedError("Subclasses must implement extractDocument")

class PdfPolicyExtractor(PolicyExtractor):
    """
    Local PDF policy extractor that reads text with page numbers and sections.
    Strictly validates PDF header and structure and fails closed on malformed or empty PDF files.
    Never decodes arbitrary bytes into fake policy citations.
    """

    def extractDocument(self, documentId: str, content: bytes) -> PolicyDocument:
        if not content or len(content) < 32:
            raise ValueError(f"Empty or corrupted PDF document: {documentId}")

        if not content.startswith(b"%PDF-"):
            raise ValueError(f"Invalid PDF header in document: {documentId}")

        sections: List[PolicySection] = []
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content))
            if not reader.pages:
                raise ValueError(f"PDF document contains zero pages: {documentId}")

            for pageNum, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                lines = [line.strip() for line in text.split("\n") if line.strip()]
                currentSection = "General requirements"
                sectionLines: List[str] = []
                for line in lines:
                    if line.isupper() or line.endswith(":") or line.startswith("Section"):
                        if sectionLines:
                            sections.append(PolicySection(documentId, pageNum, currentSection, " ".join(sectionLines)))
                            sectionLines = []
                        currentSection = line.rstrip(":")
                    else:
                        sectionLines.append(line)
                if sectionLines:
                    sections.append(PolicySection(documentId, pageNum, currentSection, " ".join(sectionLines)))
        except Exception as exc:
            if isinstance(exc, ValueError):
                raise
            raise ValueError(f"Failed to parse PDF document {documentId}: {exc}")

        if not sections:
            raise ValueError(f"No readable text sections found in PDF document: {documentId}")

        return PolicyDocument(documentId, sections)

class PolicyIndex:
    """
    Indexes policy sections and resolves relevant citations for action codes.
    """

    def __init__(self) -> None:
        self.sections: List[PolicySection] = []

    def indexDocument(self, document: PolicyDocument) -> None:
        self.sections.extend(document.sections)

    def findCitation(self, actionCode: str) -> Optional[Dict[str, Any]]:
        keywordMap = {
            "selectProduct": ["inspect", "surface flaws", "inspection"],
            "selectBox": ["box", "corrugated", "clearance"],
            "addProtection": ["bubble wrap", "cushioning", "two complete layers", "layers"],
            "placeProduct": ["center", "upright", "inside box"],
            "sealBox": ["seal", "tape", "h tape", "flaps"],
            "attachLabel": ["label", "fragile", "sticker"]
        }

        keywords = keywordMap.get(actionCode, [])
        for section in self.sections:
            lowerText = section.text.lower()
            lowerSec = section.section.lower()
            for kw in keywords:
                if kw in lowerText or kw in lowerSec:
                    # Return exact citation shape conforming to policyCitation schema
                    return {
                        "documentId": section.documentId,
                        "page": section.page,
                        "section": section.section,
                        "excerpt": section.text[:120].strip()
                    }
        return None
