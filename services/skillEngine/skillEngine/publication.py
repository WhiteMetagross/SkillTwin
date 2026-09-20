import copy
import hashlib
import json
import os
from typing import Any, Dict, List, Optional

from .audioService import AmazonPollyService, AudioSynthesisService
from .storage import S3StorageAdapter, StorageAdapter
from .translationService import AmazonTranslateService, TranslationService
from .validator import validateSchema


class PublicationService:
    def __init__(
        self,
        translator: TranslationService,
        audioService: AudioSynthesisService,
        storage: StorageAdapter,
    ) -> None:
        self.translator = translator
        self.audioService = audioService
        self.storage = storage

    @staticmethod
    def approvedContentHash(skill: Dict[str, Any]) -> str:
        canonical = json.dumps(
            skill,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def publishApprovedSkill(
        self,
        approvedSkill: Dict[str, Any],
        sopPdfKeys: List[str],
        targetLanguage: str = "hiIN",
    ) -> Dict[str, Any]:
        valid, error = validateSchema("skillPackage", approvedSkill)
        if not valid:
            raise ValueError(f"Invalid approved skill package: {error}")
        if approvedSkill.get("status") != "approved" or approvedSkill.get("version", 0) <= 0:
            raise ValueError("Publication requires an approved immutable skill version")
        if not sopPdfKeys or not all(isinstance(key, str) and key for key in sopPdfKeys):
            raise ValueError("At least one SOP PDF export key is required")
        if not all(self.storage.assetExists(key) for key in sopPdfKeys):
            raise ValueError("Every SOP PDF export key must exist before publication")

        approvedHash = self.approvedContentHash(approvedSkill)
        skillId = approvedSkill["skillId"]
        version = approvedSkill["version"]
        prefix = f"skills/{skillId}/versions/v{version}/publication/{approvedHash}"
        manifestKey = f"{prefix}/manifest.json"
        if self.storage.assetExists(manifestKey):
            manifest = json.loads(self.storage.readAsset(manifestKey).decode("utf-8"))
            self._verifyExistingManifest(manifest, approvedHash, version)
            return manifest

        translations = self.translator.translateApprovedSkill(
            approvedSkill,
            targetLanguage=targetLanguage,
        )
        if set(translations) != {step["stepId"] for step in approvedSkill["steps"]}:
            raise RuntimeError("Translation result does not cover every approved step")

        publishedSkill = copy.deepcopy(approvedSkill)
        translationKeys: Dict[str, str] = {}
        for step in publishedSkill["steps"]:
            stepId = step["stepId"]
            translated = translations[stepId]
            if not isinstance(translated, str) or not translated.strip():
                raise RuntimeError(f"Translation is empty for {stepId}")
            step["instructionHi"] = translated.strip()
            translationKey = f"{prefix}/translations/{targetLanguage}/{stepId}.txt"
            self._writeVerified(translationKey, translated.strip().encode("utf-8"))
            translationKeys[stepId] = translationKey

        audioArtifacts = self.audioService.synthesizeApprovedSkillAudio(
            publishedSkill,
            language=targetLanguage,
            storageAdapter=self.storage,
        )
        if set(audioArtifacts) != {step["stepId"] for step in publishedSkill["steps"]}:
            raise RuntimeError("Audio result does not cover every approved step")
        for step in publishedSkill["steps"]:
            step["audioKey"] = audioArtifacts[step["stepId"]].storageKey
        publishedSkill["status"] = "published"

        validPublished, publishedError = validateSchema("skillPackage", publishedSkill)
        if not validPublished:
            raise RuntimeError(f"Published skill failed schema validation: {publishedError}")
        publishedSkillKey = f"{prefix}/skillPackage.published.json"
        self._writeVerified(
            publishedSkillKey,
            json.dumps(publishedSkill, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        )

        manifest = {
            "schemaVersion": 1,
            "skillId": skillId,
            "approvedVersion": version,
            "approvedContentHash": approvedHash,
            "targetLanguage": targetLanguage,
            "translationKeys": translationKeys,
            "audioArtifacts": {
                stepId: descriptor.toDict() for stepId, descriptor in audioArtifacts.items()
            },
            "sopPdfKeys": list(sopPdfKeys),
            "publishedSkillKey": publishedSkillKey,
            "manifestKey": manifestKey,
        }
        self._writeVerified(
            manifestKey,
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        )
        return manifest

    def _writeVerified(self, key: str, payload: bytes) -> None:
        storedKey = self.storage.writeAsset(key, payload)
        if storedKey != key or self.storage.readAsset(key) != payload:
            raise RuntimeError(f"Stored publication artifact verification failed: {key}")

    def _verifyExistingManifest(
        self,
        manifest: Dict[str, Any],
        approvedHash: str,
        version: int,
    ) -> None:
        if (
            manifest.get("approvedContentHash") != approvedHash
            or manifest.get("approvedVersion") != version
        ):
            raise RuntimeError("Existing publication manifest does not match the approved snapshot")
        keys = list(manifest.get("translationKeys", {}).values())
        keys.extend(
            artifact.get("storageKey", "")
            for artifact in manifest.get("audioArtifacts", {}).values()
        )
        keys.extend(manifest.get("sopPdfKeys", []))
        keys.append(manifest.get("publishedSkillKey", ""))
        if not keys or not all(key and self.storage.assetExists(key) for key in keys):
            raise RuntimeError("Existing publication manifest references missing artifacts")


def buildProductionPublisher(environment: Optional[Dict[str, str]] = None) -> PublicationService:
    env = environment if environment is not None else os.environ
    region = env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION")
    bucket = env.get("SKILLTWIN_BUCKET")
    if not region or not bucket:
        raise RuntimeError("AWS_REGION and SKILLTWIN_BUCKET are required for publication")
    import boto3
    storage = S3StorageAdapter(bucket=bucket, s3Client=boto3.client("s3", region_name=region))
    terminology = [env["SKILL_ENGINE_TERMINOLOGY"]] if env.get("SKILL_ENGINE_TERMINOLOGY") else []
    return PublicationService(
        translator=AmazonTranslateService(
            translateClient=boto3.client("translate", region_name=region),
            terminologyNames=terminology,
        ),
        audioService=AmazonPollyService(
            pollyClient=boto3.client("polly", region_name=region),
            voiceId=env.get("SKILL_ENGINE_POLLY_VOICE", "Kajal"),
        ),
        storage=storage,
    )
