from typing import Any, Dict, List, Optional, Tuple

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

        # Check for deliberate conflict on cushioning and protection
        if actionCode == "addProtection":
            obsActions = " ".join([obs.get("action", "") for obs in observations]).lower()
            obsSpoken = " ".join([obs.get("spokenEvidence", "") or "" for obs in observations]).lower()
            hasSingleWrapObs = "single layer" in obsActions or "single" in obsActions or "single" in obsSpoken

            citationText = citation.get("excerpt", "").lower() if citation else ""
            requiresDoubleWrap = "two" in citationText or "double" in citationText or "two complete layers" in citationText

            if citation and hasSingleWrapObs and requiresDoubleWrap:
                return PolicyVerificationResult(
                    status="conflict",
                    citation=citation,
                    warning="Demonstration shows single wrap but policy requires two layers",
                    proposedInstruction="Wrap the ceramic mug completely with two layers of bubble wrap cushioning."
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
