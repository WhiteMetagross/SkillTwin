from typing import Any, Dict, Optional

class AudioArtifactDescriptor:
    def __init__(self, stepId: str, storageKey: str, mimeType: str, sizeBytes: int) -> None:
        self.stepId = stepId
        self.storageKey = storageKey
        self.mimeType = mimeType
        self.sizeBytes = sizeBytes

    def toDict(self) -> Dict[str, Any]:
        return {
            "stepId": self.stepId,
            "storageKey": self.storageKey,
            "mimeType": self.mimeType,
            "sizeBytes": self.sizeBytes
        }

class AudioSynthesisService:
    def synthesizeApprovedSkillAudio(
        self,
        skill: Dict[str, Any],
        language: str = "hiIN"
    ) -> Dict[str, AudioArtifactDescriptor]:
        raise NotImplementedError("Subclasses must implement synthesizeApprovedSkillAudio")

    def _verifyApproved(self, skill: Dict[str, Any]) -> None:
        if (
            skill.get("status") == "reviewRequired"
            or skill.get("version", 0) == 0
            or not skill.get("approvedBy")
        ):
            raise ValueError("Draft skills cannot synthesize audio. Audio synthesis is only permitted for approved skills.")

class LocalAudioSynthesisService(AudioSynthesisService):
    """
    Deterministic local audio synthesis service.
    Generates audio artifact descriptors for approved skills without calling external cloud services.
    """

    def synthesizeApprovedSkillAudio(
        self,
        skill: Dict[str, Any],
        language: str = "hiIN"
    ) -> Dict[str, AudioArtifactDescriptor]:
        self._verifyApproved(skill)
        skillId = skill.get("skillId", "skill-default")
        version = skill.get("version", 1)

        result: Dict[str, AudioArtifactDescriptor] = {}
        for step in skill.get("steps", []):
            stepId = step.get("stepId", "")
            storageKey = f"skills/{skillId}/versions/v{version}/audio/{language}/{stepId}.mp3"
            result[stepId] = AudioArtifactDescriptor(
                stepId=stepId,
                storageKey=storageKey,
                mimeType="audio/mpeg",
                sizeBytes=16384
            )
        return result

class AmazonPollyService(AudioSynthesisService):
    """
    Adapter invoking Amazon Polly to synthesize audio narration for approved skills.
    """

    def __init__(self, pollyClient: Optional[Any] = None) -> None:
        self.pollyClient = pollyClient

    def _getClient(self) -> Any:
        if self.pollyClient is not None:
            return self.pollyClient
        import boto3
        return boto3.client("polly")

    def synthesizeApprovedSkillAudio(
        self,
        skill: Dict[str, Any],
        language: str = "hiIN"
    ) -> Dict[str, AudioArtifactDescriptor]:
        self._verifyApproved(skill)
        client = self._getClient()
        skillId = skill.get("skillId", "skill-default")
        version = skill.get("version", 1)

        result: Dict[str, AudioArtifactDescriptor] = {}
        for step in skill.get("steps", []):
            stepId = step.get("stepId", "")
            text = step.get("instructionHi") or step.get("instruction", "")
            if not text:
                continue

            response = client.synthesize_speech(
                Engine="neural",
                LanguageCode="hi-IN" if "hi" in language else "en-IN",
                OutputFormat="mp3",
                Text=text,
                VoiceId="Aditi" if "hi" in language else "Kajal"
            )

            audioStream = response.get("AudioStream")
            audioBytes = audioStream.read() if audioStream else b""
            storageKey = f"skills/{skillId}/versions/v{version}/audio/{language}/{stepId}.mp3"

            result[stepId] = AudioArtifactDescriptor(
                stepId=stepId,
                storageKey=storageKey,
                mimeType="audio/mpeg",
                sizeBytes=len(audioBytes) if audioBytes else 16384
            )

        return result
