from typing import Any, Dict, List, Optional

class TranslationService:
    def translateApprovedSkill(
        self,
        skill: Dict[str, Any],
        targetLanguage: str = "hiIN"
    ) -> Dict[str, str]:
        raise NotImplementedError("Subclasses must implement translateApprovedSkill")

    def _verifyApproved(self, skill: Dict[str, Any]) -> None:
        if (
            skill.get("status") != "approved"
            or not isinstance(skill.get("version"), int)
            or skill.get("version", 0) <= 0
            or not isinstance(skill.get("approvedBy"), str)
            or not skill.get("approvedBy", "").strip()
        ):
            raise ValueError("Draft skills cannot be translated. Translation is only permitted for approved skills.")
        steps = skill.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError("Approved skill has no translatable steps")

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
            if not stepId or not translated.strip():
                raise ValueError("Every approved step must have a nonempty translation")
            translations[stepId] = translated
        return translations

class AmazonTranslateService(TranslationService):
    """
    Adapter invoking Amazon Translate for approved skill instructions.
    """

    def __init__(
        self,
        translateClient: Optional[Any] = None,
        terminologyNames: Optional[List[str]] = None,
        fixedTerms: Optional[List[str]] = None,
    ) -> None:
        self.translateClient = translateClient
        self.terminologyNames = terminologyNames or []
        self.fixedTerms = fixedTerms if fixedTerms is not None else ["H tape", "QR", "SKU"]

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
            if not stepId or not isinstance(text, str) or not text.strip():
                raise ValueError("Every approved step must have a nonempty English instruction")
            request = dict(
                Text=text,
                SourceLanguageCode="en",
                TargetLanguageCode=targetLangCode
            )
            if self.terminologyNames:
                request["TerminologyNames"] = self.terminologyNames
            response = client.translate_text(**request)
            translated = response.get("TranslatedText")
            if not isinstance(translated, str) or not translated.strip():
                raise RuntimeError(f"Amazon Translate returned an empty result for {stepId}")
            for term in self.fixedTerms:
                if term.lower() in text.lower() and term.lower() not in translated.lower():
                    raise RuntimeError(f"Translation did not preserve fixed technical term '{term}' for {stepId}")
            translations[stepId] = translated.strip()
        if len(translations) != len(skill["steps"]):
            raise RuntimeError("Amazon Translate did not return every approved step")
        return translations
