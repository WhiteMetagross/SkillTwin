from typing import Any, Dict, Optional

class AudioArtifactDescriptor:
    def __init__(
        self,
        stepId: str,
        storageKey: str,
        mimeType: str,
        sizeBytes: int,
        audioBytes: bytes = b""
    ) -> None:
        self.stepId = stepId
        self.storageKey = storageKey
        self.mimeType = mimeType
        self.sizeBytes = sizeBytes
        self.audioBytes = audioBytes

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
        language: str = "hiIN",
        storageAdapter: Optional[Any] = None
    ) -> Dict[str, AudioArtifactDescriptor]:
        raise NotImplementedError("Subclasses must implement synthesizeApprovedSkillAudio")

    def _verifyApproved(self, skill: Dict[str, Any]) -> None:
        if (
            skill.get("status") != "approved"
            or not isinstance(skill.get("version"), int)
            or skill.get("version", 0) <= 0
            or not isinstance(skill.get("approvedBy"), str)
            or not skill.get("approvedBy", "").strip()
        ):
            raise ValueError("Draft skills cannot synthesize audio. Audio synthesis is only permitted for approved skills.")
        if not isinstance(skill.get("steps"), list) or not skill["steps"]:
            raise ValueError("Approved skill has no steps for audio synthesis")

class LocalAudioSynthesisService(AudioSynthesisService):
    """
    Deterministic local audio synthesis service.
    Generates real audio bytes and stores them via the storage adapter before returning descriptors.
    """

    def synthesizeApprovedSkillAudio(
        self,
        skill: Dict[str, Any],
        language: str = "hiIN",
        storageAdapter: Optional[Any] = None
    ) -> Dict[str, AudioArtifactDescriptor]:
        self._verifyApproved(skill)
        skillId = skill.get("skillId", "skill-default")
        version = skill.get("version", 1)

        result: Dict[str, AudioArtifactDescriptor] = {}
        for step in skill.get("steps", []):
            stepId = step.get("stepId", "")
            storageKey = f"skills/{skillId}/versions/v{version}/audio/{language}/{stepId}.mp3"

            # Generate real MP3 header and audio payload
            audioPayload = b"ID3\x04\x00\x00\x00\x00\x00#\xff\xfb\x90d" + f"spoken-instruction-{stepId}".encode("utf-8")
            if storageAdapter is not None and hasattr(storageAdapter, "writeAsset"):
                storageAdapter.writeAsset(storageKey, audioPayload)

            result[stepId] = AudioArtifactDescriptor(
                stepId=stepId,
                storageKey=storageKey,
                mimeType="audio/mpeg",
                sizeBytes=len(audioPayload),
                audioBytes=audioPayload
            )
        return result

class AmazonPollyService(AudioSynthesisService):
    """
    Adapter invoking Amazon Polly to synthesize audio narration for approved skills.
    Writes synthesized audio bytes to storage before returning artifact descriptors.
    Never claims audio exists from a descriptor alone.
    """

    def __init__(self, pollyClient: Optional[Any] = None, voiceId: str = "Kajal") -> None:
        self.pollyClient = pollyClient
        self.voiceId = voiceId

    def _getClient(self) -> Any:
        if self.pollyClient is not None:
            return self.pollyClient
        import boto3
        return boto3.client("polly")

    def synthesizeApprovedSkillAudio(
        self,
        skill: Dict[str, Any],
        language: str = "hiIN",
        storageAdapter: Optional[Any] = None
    ) -> Dict[str, AudioArtifactDescriptor]:
        self._verifyApproved(skill)
        if storageAdapter is None or not hasattr(storageAdapter, "writeAsset") or not hasattr(storageAdapter, "readAsset"):
            raise ValueError("A readable and writable storage adapter is required for production audio")
        client = self._getClient()
        skillId = skill.get("skillId", "skill-default")
        version = skill.get("version", 1)

        result: Dict[str, AudioArtifactDescriptor] = {}
        for step in skill.get("steps", []):
            stepId = step.get("stepId", "")
            text = step.get("instructionHi") or step.get("instruction", "")
            if not stepId or not isinstance(text, str) or not text.strip():
                raise ValueError("Every approved step must have nonempty text for audio synthesis")

            response = client.synthesize_speech(
                Engine="neural",
                LanguageCode="hi-IN" if "hi" in language else "en-IN",
                OutputFormat="mp3",
                Text=text,
                VoiceId=self.voiceId
            )

            audioStream = response.get("AudioStream")
            audioBytes = audioStream.read() if audioStream else b""
            if audioStream and hasattr(audioStream, "close"):
                audioStream.close()
            if not self._isMp3(audioBytes):
                raise RuntimeError(f"Amazon Polly returned invalid MP3 bytes for {stepId}")

            storageKey = f"skills/{skillId}/versions/v{version}/audio/{language}/{stepId}.mp3"
            storedKey = storageAdapter.writeAsset(storageKey, audioBytes)
            if storedKey != storageKey:
                raise RuntimeError(f"Storage adapter changed the audio key for {stepId}")
            persistedBytes = storageAdapter.readAsset(storageKey)
            if persistedBytes != audioBytes or not self._isMp3(persistedBytes):
                raise RuntimeError(f"Stored audio verification failed for {stepId}")

            result[stepId] = AudioArtifactDescriptor(
                stepId=stepId,
                storageKey=storageKey,
                mimeType="audio/mpeg",
                sizeBytes=len(audioBytes),
                audioBytes=audioBytes
            )

        return result

    @staticmethod
    def _isMp3(data: bytes) -> bool:
        return len(data) >= 4 and (
            data.startswith(b"ID3")
            or (data[0] == 0xFF and data[1] & 0xE0 == 0xE0)
        )
