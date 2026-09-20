import argparse
import json
import os
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional

from .bedrockCaller import BedrockModelCaller
from .mockAdapter import SkillEngineAdapter
from .policyExtractor import PdfPolicyExtractor, PolicyIndex
from .policyVerifier import PolicyVerifier
from .storage import S3StorageAdapter, StorageAdapter
from .textractExtractor import TextractPolicyExtractor
from .validator import validateSchema


class ProductionSkillEngine:
    def __init__(
        self,
        storage: StorageAdapter,
        bucket: str,
        modelCaller: BedrockModelCaller,
        pdfExtractor: Optional[PdfPolicyExtractor] = None,
        textractExtractor: Optional[TextractPolicyExtractor] = None,
    ) -> None:
        if not bucket:
            raise ValueError("Policy bucket is required")
        self.storage = storage
        self.bucket = bucket
        self.modelCaller = modelCaller
        self.pdfExtractor = pdfExtractor or PdfPolicyExtractor()
        self.textractExtractor = textractExtractor or TextractPolicyExtractor()

    def composeFromStorage(
        self,
        evidenceBundleKey: str,
        policyDocumentKeys: List[str],
    ) -> Dict[str, Any]:
        if not evidenceBundleKey or not policyDocumentKeys:
            raise ValueError("evidenceBundleKey and at least one policy document key are required")
        try:
            bundle = json.loads(self.storage.readAsset(evidenceBundleKey).decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"Evidence bundle could not be loaded: {exc}") from exc
        valid, error = validateSchema("evidenceBundle", bundle)
        if not valid:
            raise ValueError(f"Invalid evidence bundle: {error}")

        index = PolicyIndex()
        for storageKey in policyDocumentKeys:
            documentId = PurePosixPath(storageKey).stem
            if not documentId:
                raise ValueError(f"Invalid policy document key: {storageKey}")
            content = self.storage.readAsset(storageKey)
            try:
                document = self.pdfExtractor.extractDocument(documentId, content)
            except ValueError as exc:
                if "No readable text sections" not in str(exc):
                    raise
                document = self.textractExtractor.extractS3Document(
                    documentId=documentId,
                    bucket=self.bucket,
                    storageKey=storageKey,
                )
            index.indexDocument(document)

        adapter = SkillEngineAdapter(
            modelCaller=self.modelCaller,
            policyVerifier=PolicyVerifier(),
        )
        draft = adapter.composeDraft(bundle, customCitations=index.citationsByAction())
        outputKey = f"skills/{bundle['skillId']}/drafts/v0/skillPackage.json"
        encoded = json.dumps(draft, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.storage.writeAsset(outputKey, encoded)
        return {"skillPackageKey": outputKey, "skillPackage": draft}


def buildProductionEngine(environment: Optional[Dict[str, str]] = None) -> ProductionSkillEngine:
    env = environment if environment is not None else os.environ
    region = env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION")
    bucket = env.get("SKILLTWIN_BUCKET")
    modelId = env.get("SKILL_ENGINE_MODEL_ID")
    missing = [name for name, value in {
        "AWS_REGION": region,
        "SKILLTWIN_BUCKET": bucket,
        "SKILL_ENGINE_MODEL_ID": modelId,
    }.items() if not value]
    if missing:
        raise RuntimeError(f"Missing production configuration: {', '.join(missing)}")

    import boto3
    s3Client = boto3.client("s3", region_name=region)
    bedrockClient = boto3.client("bedrock-runtime", region_name=region)
    textractClient = boto3.client("textract", region_name=region)
    storage = S3StorageAdapter(bucket=bucket, s3Client=s3Client)
    return ProductionSkillEngine(
        storage=storage,
        bucket=bucket,
        modelCaller=BedrockModelCaller(
            bedrockClient=bedrockClient,
            modelId=modelId,
            allowFallback=False,
            strictGrounding=True,
        ),
        textractExtractor=TextractPolicyExtractor(textractClient=textractClient),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compose a grounded skill draft from S3 assets")
    parser.add_argument("--evidence-bundle-key", required=True)
    parser.add_argument("--policy-document-key", action="append", required=True)
    args = parser.parse_args()
    result = buildProductionEngine().composeFromStorage(
        evidenceBundleKey=args.evidence_bundle_key,
        policyDocumentKeys=args.policy_document_key,
    )
    print(json.dumps({"skillPackageKey": result["skillPackageKey"]}))


if __name__ == "__main__":
    main()
