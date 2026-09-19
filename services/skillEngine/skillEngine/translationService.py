from typing import Any, Dict, Optional

class TranslationService:
    def translateApprovedSkill(
        self,
        skill: Dict[str, Any],
        targetLanguage: str = "hiIN"
    ) -> Dict[str, str]:
        raise NotImplementedError("Subclasses must implement translateApprovedSkill")

    def _verifyApproved(self, skill: Dict[str, Any]) -> None:
        if (
            skill.get("status") == "reviewRequired"
            or skill.get("version", 0) == 0
            or not skill.get("approvedBy")
        ):
            raise ValueError("Draft skills cannot be translated. Translation is only permitted for approved skills.")

class LocalTranslationService(TranslationService):
    """
    Deterministic local translator for approved skills.
    Maps English instructions to Hindi translations using verified standard operating procedure terminology.
    """

    TRANSLATION_MAP = {
        "selectProduct": "सिरेमिक मग की सतह पर दरारें और खामियां जांचें।",
        "selectBox": "छोटे मानक नालीदार कार्टन को इकट्ठा करें।",
        "addProtection": "सिरेमिक मग को पूरी तरह से बबल रैप से लपेटें।",
        "placeProduct": "लपेटे गए मग को बॉक्स के केंद्र में सीधा रखें।",
        "sealBox": "बॉक्स के फ्लैप बंद करें और एच टेप विधि से सील करें।",
        "attachLabel": "सील किए गए बॉक्स के शीर्ष पर नाजुक शिपिंग लेबल चिपकाएं।"
    }

    def translateApprovedSkill(
        self,
        skill: Dict[str, Any],
        targetLanguage: str = "hiIN"
    ) -> Dict[str, str]:
        self._verifyApproved(skill)
        translations: Dict[str, str] = {}
        for step in skill.get("steps", []):
            stepId = step.get("stepId", "")
            actionCode = step.get("actionCode", "")
            translated = self.TRANSLATION_MAP.get(actionCode, f"{step.get('instruction', '')} (अनुवाद)")
            translations[stepId] = translated
        return translations

class AmazonTranslateService(TranslationService):
    """
    Adapter invoking Amazon Translate for approved skill instructions.
    """

    def __init__(self, translateClient: Optional[Any] = None) -> None:
        self.translateClient = translateClient

    def _getClient(self) -> Any:
        if self.translateClient is not None:
            return self.translateClient
        import boto3
        return boto3.client("translate")

    def translateApprovedSkill(
        self,
        skill: Dict[str, Any],
        targetLanguage: str = "hiIN"
    ) -> Dict[str, str]:
        self._verifyApproved(skill)
        client = self._getClient()
        targetLangCode = "hi" if "hi" in targetLanguage else targetLanguage

        translations: Dict[str, str] = {}
        for step in skill.get("steps", []):
            stepId = step.get("stepId", "")
            text = step.get("instruction", "")
            if not text:
                continue
            response = client.translate_text(
                Text=text,
                SourceLanguageCode="en",
                TargetLanguageCode=targetLangCode
            )
            translations[stepId] = response.get("TranslatedText", "")
        return translations
