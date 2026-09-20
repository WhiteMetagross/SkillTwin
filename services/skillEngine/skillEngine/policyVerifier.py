import re
from typing import Any, Dict, List, Optional

class PolicyVerificationResult:
    def __init__(
        self,
        status: str,
        citation: Optional[Dict[str, Any]],
        warning: Optional[str],
        proposedInstruction: Optional[str]
    ) -> None:
        self.status = status
        self.citation = citation
        self.warning = warning
        self.proposedInstruction = proposedInstruction

class PolicyVerifier:
    """
    Verifies proposed actions against visual observations, spoken audio evidence, and policy text.
    Detects deliberate or accidental conflicts between recorded practice and formal policy.
    """

    def verifyAction(
        self,
        actionCode: str,
        observations: List[Dict[str, Any]],
        citation: Optional[Dict[str, Any]],
        defaultInstruction: str
    ) -> PolicyVerificationResult:
        if not observations:
            return PolicyVerificationResult(
                status="needsReview",
                citation=citation,
                warning="Action slot lacks demonstration evidence and requires supervisor review",
                proposedInstruction=defaultInstruction
            )

        hasVisibleEvidence = any(
            observation.get("visibleObjects") and str(observation.get("action", "")).strip()
            for observation in observations
        )
        if not hasVisibleEvidence:
            return PolicyVerificationResult(
                status="needsReview",
                citation=citation,
                warning="Visual evidence is missing or ambiguous and requires supervisor review",
                proposedInstruction=defaultInstruction,
            )

        if actionCode == "addProtection":
            obsActions = " ".join([obs.get("action", "") for obs in observations]).lower()
            obsSpoken = " ".join([obs.get("spokenEvidence", "") or "" for obs in observations]).lower()
            citationText = citation.get("excerpt", "").lower() if citation else ""
            observedLayers = self._extractLayerCount(f"{obsActions} {obsSpoken}")
            requiredLayers = self._extractLayerCount(citationText)

            if citation and observedLayers is not None and requiredLayers is not None and observedLayers < requiredLayers:
                exactRequirement = str(citation.get("excerpt", "")).strip()
                observedLabel = "single wrap" if observedLayers == 1 else f"{observedLayers} layers"
                requiredLabel = "two layers" if requiredLayers == 2 else f"{requiredLayers} layers"
                return PolicyVerificationResult(
                    status="conflict",
                    citation=citation,
                    warning=(
                        f"Demonstration shows {observedLabel} but policy requires "
                        f"{requiredLabel}: \"{exactRequirement}\""
                    ),
                    proposedInstruction=f"Follow the policy requirement: {exactRequirement}",
                )

        if not citation:
            return PolicyVerificationResult(
                status="notFound",
                citation=None,
                warning=None,
                proposedInstruction=defaultInstruction
            )

        return PolicyVerificationResult(
            status="supported",
            citation=citation,
            warning=None,
            proposedInstruction=defaultInstruction
        )

    @staticmethod
    def _extractLayerCount(text: str) -> Optional[int]:
        normalized = text.lower().replace("double", "two").replace("single", "one")
        match = re.search(r"\b(one|two|three|four|\d+)\s+(?:complete\s+)?layers?\b", normalized)
        if not match:
            return None
        words = {"one": 1, "two": 2, "three": 3, "four": 4}
        token = match.group(1)
        return words.get(token, int(token) if token.isdigit() else None)
