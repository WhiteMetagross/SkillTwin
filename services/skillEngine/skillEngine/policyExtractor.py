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

    def findCitations(self, actionCode: str, limit: int = 3) -> List[Dict[str, Any]]:
        keywordMap = {
            "selectProduct": ["inspect", "surface flaws", "inspection"],
            "selectBox": ["box", "corrugated", "clearance"],
            "addProtection": ["bubble wrap", "cushioning", "two complete layers", "layers"],
            "placeProduct": ["center", "upright", "inside box"],
            "sealBox": ["seal", "tape", "h tape", "flaps"],
            "attachLabel": ["label", "fragile", "sticker"]
        }

        if limit < 1:
            return []
        keywords = keywordMap.get(actionCode, [])
        ranked: List[tuple[int, int, PolicySection]] = []
        for section in self.sections:
            lowerText = section.text.lower()
            lowerSec = section.section.lower()
            textHits = sum(1 for keyword in keywords if keyword in lowerText)
            headingHits = sum(1 for keyword in keywords if keyword in lowerSec)
            score = textHits + (headingHits * 2)
            if score:
                ranked.append((score, -section.page, section))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [
            {
                "documentId": section.documentId,
                "page": section.page,
                "section": section.section,
                "excerpt": section.text.strip()[:1000],
            }
            for _, _, section in ranked[:limit]
        ]

    def findCitation(self, actionCode: str) -> Optional[Dict[str, Any]]:
        citations = self.findCitations(actionCode, limit=1)
        return citations[0] if citations else None

    def citationsByAction(self) -> Dict[str, Optional[Dict[str, Any]]]:
        return {
            actionCode: self.findCitation(actionCode)
            for actionCode in (
                "selectProduct",
                "selectBox",
                "addProtection",
                "placeProduct",
                "sealBox",
                "attachLabel",
            )
        }
