from typing import Any, Dict, List, Optional
from .modelCaller import LocalModelCaller, ModelCaller
from .observationMapper import TEMPLATE_ACTIONS, mapObservationsToActionSlots
from .policyExtractor import PdfPolicyExtractor, PolicyDocument, PolicyIndex, PolicySection
from .policyVerifier import PolicyVerificationResult, PolicyVerifier
from .validator import validateActionOrder, validateSchema

class PolicyRetriever:
    def retrievePolicyCitations(self, skillId: str) -> Dict[str, Any]:
        raise NotImplementedError("Subclasses must implement retrievePolicyCitations")

class MockPolicyRetriever(PolicyRetriever):
    """
    Default policy retriever returning verified standard citations for fragile packing.
    """

    def retrievePolicyCitations(self, skillId: str) -> Dict[str, Any]:
        return {
            "selectProduct": {
                "documentId": "doc-packing-policy-001",
                "page": 2,
                "section": "Item inspection",
                "excerpt": "Inspect fragile items for surface flaws before handling."
            },
            "selectBox": {
                "documentId": "doc-packing-policy-001",
                "page": 3,
                "section": "Box sizing",
                "excerpt": "Select a box that provides at least two inches of clearance on all sides."
            },
            "addProtection": {
                "documentId": "doc-packing-policy-001",
                "page": 4,
                "section": "Cushioning",
                "excerpt": "Fragile ceramics require two complete layers of bubble wrap."
            },
            "sealBox": {
                "documentId": "doc-packing-policy-001",
                "page": 5,
                "section": "Sealing",
                "excerpt": "Seal center flap and edges using H tape method."
            },
            "attachLabel": {
                "documentId": "doc-packing-policy-001",
                "page": 6,
                "section": "Labeling",
                "excerpt": "Affix fragile shipping label visibly on top flap."
            }
        }

class MockSkillEngineAdapter:
    """
    Adapter for skill engine service.
    Maps evidence bundle observations across videos into the six step fragile packing template.
    Merges repeated actions, preserves observation traceability, evaluates policy citations and conflicts,
    and produces schema valid draft skill packages.
    """

    def __init__(
        self,
        policyRetriever: Optional[PolicyRetriever] = None,
        modelCaller: Optional[ModelCaller] = None,
        policyVerifier: Optional[PolicyVerifier] = None
    ) -> None:
        self.policyRetriever = policyRetriever or MockPolicyRetriever()
        self.modelCaller = modelCaller or LocalModelCaller()
        self.policyVerifier = policyVerifier or PolicyVerifier()

    def composeDraft(
        self,
        bundle: Dict[str, Any],
        customCitations: Optional[Dict[str, Optional[Dict[str, Any]]]] = None
    ) -> Dict[str, Any]:
        validBundle, bundleError = validateSchema("evidenceBundle", bundle)
        if not validBundle:
            raise ValueError(f"Invalid evidence bundle: {bundleError}")

        skillId = bundle["skillId"]
        observations = bundle.get("observations", [])

        # Map and merge observations into six fragile packing action slots
        actionSlots = mapObservationsToActionSlots(observations)
        observationsByAction = {slot.actionCode: slot.observations for slot in actionSlots}

        # Resolve policy citations
        if customCitations is not None:
            citations = customCitations
        else:
            citations = self.policyRetriever.retrievePolicyCitations(skillId)

        # Synthesize title, materials, prerequisites, and instructions from evidence and policy
        composition = self.modelCaller.composeSkillContent(
            skillId,
            observationsByAction,
            citations
        )

        checkpointRequiredMap = {
            "selectProduct": False,
            "selectBox": False,
            "addProtection": True,
            "placeProduct": False,
            "sealBox": False,
            "attachLabel": True
        }

        steps: List[Dict[str, Any]] = []

        for index, slot in enumerate(actionSlots):
            seq = index + 1
            actionCode = slot.actionCode
            rep = slot.representative
            citation = citations.get(actionCode)
            baseInstruction = composition.instructions.get(actionCode, f"Execute step {seq}")

            verification = self.policyVerifier.verifyAction(
                actionCode=actionCode,
                observations=slot.observations,
                citation=citation,
                defaultInstruction=baseInstruction
            )

            finalInstruction = verification.proposedInstruction or baseInstruction
            checkpointReq = checkpointRequiredMap.get(actionCode, False)

            steps.append({
                "stepId": f"step-00{seq}",
                "sequence": seq,
                "actionCode": actionCode,
                "instruction": finalInstruction,
                "instructionHi": None,
                "sourceVideoId": rep["videoId"] if rep else None,
                "startMs": rep["startMs"] if rep else None,
                "endMs": rep["endMs"] if rep else None,
                "referenceFrameKey": rep["referenceFrameKey"] if rep else None,
                "confidence": rep["confidence"] if rep else None,
                "policyStatus": verification.status,
                "policyCitation": verification.citation,
                "warning": verification.warning,
                "checkpointRequired": checkpointReq,
                "audioKey": None,
                "evidenceObservationIds": slot.observationIds
            })

        if not validateActionOrder(steps):
            raise ValueError("Draft steps do not match the required six step template sequence")

        draft = {
            "schemaVersion": 1,
            "skillId": skillId,
            "title": composition.title,
            "workflowType": "fragilePackingV1",
            "status": "reviewRequired",
            "version": 0,
            "materials": composition.materials,
            "prerequisites": composition.prerequisites,
            "steps": steps,
            "approvedBy": None,
            "approvedAt": None
        }

        validDraft, draftError = validateSchema("skillPackage", draft)
        if not validDraft:
            raise ValueError(f"Composed draft failed schema validation: {draftError}")

        return draft
