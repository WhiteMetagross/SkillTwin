from typing import Any, Dict, List, Optional
from .policyExtractor import PolicyDocument, PolicyExtractor, PolicySection

class TextractPolicyExtractor(PolicyExtractor):
    """
    Adapter using Amazon Textract for scanned and image policy documents.
    Extracts pages and lines from Textract DetectDocumentText or AnalyzeDocument blocks.
    """

    def __init__(self, textractClient: Optional[Any] = None) -> None:
        self.textractClient = textractClient

    def _getClient(self) -> Any:
        if self.textractClient is not None:
            return self.textractClient
        import boto3
        return boto3.client("textract")

    def extractDocument(self, documentId: str, content: bytes) -> PolicyDocument:
        client = self._getClient()
        response = client.detect_document_text(
            Document={"Bytes": content}
        )
        return self.parseTextractBlocks(documentId, response.get("Blocks", []))

    def parseTextractBlocks(self, documentId: str, blocks: List[Dict[str, Any]]) -> PolicyDocument:
        sections: List[PolicySection] = []
        currentPage = 1
        pageLines: Dict[int, List[str]] = {}

        for block in blocks:
            bType = block.get("BlockType")
            if bType == "PAGE":
                currentPage = block.get("Page", currentPage)
            elif bType == "LINE":
                pNum = block.get("Page", currentPage)
                text = block.get("Text", "").strip()
                if text:
                    pageLines.setdefault(pNum, []).append(text)

        for pageNum, lines in sorted(pageLines.items()):
            fullPageText = " ".join(lines)
            sectionName = lines[0] if lines else "Scanned section"
            sections.append(PolicySection(documentId, pageNum, sectionName, fullPageText))

        if not sections:
            sections.append(PolicySection(documentId, 1, "Scanned section", "No text detected"))

        return PolicyDocument(documentId, sections)
