import time
from typing import Any, Callable, Dict, List, Optional
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
        if not content:
            raise ValueError(f"Empty scanned policy document: {documentId}")
        client = self._getClient()
        response = client.detect_document_text(
            Document={"Bytes": content}
        )
        return self.parseTextractBlocks(documentId, response.get("Blocks", []))

    def startS3Document(self, documentId: str, bucket: str, storageKey: str) -> str:
        if not documentId or not bucket or not storageKey:
            raise ValueError("documentId, bucket, and storageKey are required")
        response = self._getClient().start_document_text_detection(
            DocumentLocation={"S3Object": {"Bucket": bucket, "Name": storageKey}},
            JobTag=documentId[:64],
        )
        jobId = response.get("JobId")
        if not isinstance(jobId, str) or not jobId:
            raise RuntimeError("Textract did not return a job ID")
        return jobId

    def getS3DocumentStatus(self, jobId: str) -> str:
        response = self._getClient().get_document_text_detection(JobId=jobId, MaxResults=1)
        status = response.get("JobStatus")
        if status not in {"IN_PROGRESS", "SUCCEEDED", "FAILED", "PARTIAL_SUCCESS"}:
            raise RuntimeError(f"Unknown Textract job status: {status}")
        return status

    def extractS3Document(
        self,
        documentId: str,
        bucket: str,
        storageKey: str,
        maxPolls: int = 120,
        pollIntervalSeconds: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> PolicyDocument:
        if maxPolls < 1 or pollIntervalSeconds < 0:
            raise ValueError("Textract polling bounds are invalid")
        client = self._getClient()
        jobId = self.startS3Document(documentId, bucket, storageKey)
        response: Dict[str, Any] = {}
        for attempt in range(maxPolls):
            response = client.get_document_text_detection(JobId=jobId)
            status = response.get("JobStatus")
            if status in {"SUCCEEDED", "PARTIAL_SUCCESS"}:
                break
            if status == "FAILED":
                raise RuntimeError(
                    f"Textract job {jobId} failed: {response.get('StatusMessage', 'unknown error')}"
                )
            if status != "IN_PROGRESS":
                raise RuntimeError(f"Unknown Textract job status: {status}")
            if attempt + 1 < maxPolls:
                sleep(pollIntervalSeconds)
        else:
            raise TimeoutError(f"Textract job {jobId} did not finish within {maxPolls} polls")

        blocks = list(response.get("Blocks", []))
        nextToken = response.get("NextToken")
        while nextToken:
            response = client.get_document_text_detection(JobId=jobId, NextToken=nextToken)
            if response.get("JobStatus") not in {"SUCCEEDED", "PARTIAL_SUCCESS"}:
                raise RuntimeError(f"Textract pagination failed for job {jobId}")
            blocks.extend(response.get("Blocks", []))
            nextToken = response.get("NextToken")
        return self.parseTextractBlocks(documentId, blocks)

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
            raise ValueError(f"Textract found no readable text in document: {documentId}")

        return PolicyDocument(documentId, sections)
