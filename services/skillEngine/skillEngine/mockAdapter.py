from typing import Any, Dict, List, Optional
from .validator import validateSchema, validateActionOrder

class PolicyRetriever:
    def retrievePolicyCitations(self, skillId: str) -> Dict[str, Any]:
        raise NotImplementedError("Live policy retrieval is not implemented in mock")

class MockPolicyRetriever(PolicyRetriever):
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

class ModelCaller:
    def composeInstructions(self, observations: List[Dict[str, Any]]) -> Dict[str, str]:
        raise NotImplementedError("Live model caller is not implemented in mock")

class MockModelCaller(ModelCaller):
    def composeInstructions(self, observations: List[Dict[str, Any]]) -> Dict[str, str]:
        return {
            "selectProduct": "Inspect the ceramic mug for surface cracks and defects.",
            "selectBox": "Assemble the small standard corrugated carton.",
            "addProtection": "Wrap the ceramic mug completely with bubble wrap cushioning.",
            "placeProduct": "Place the wrapped ceramic mug upright in the center of the box.",
            "sealBox": "Close box flaps and seal center seam and edges using H tape method.",
            "attachLabel": "Affix fragile shipping label visibly on the top face of the sealed box."
        }

class MockSkillEngineAdapter:
    """
    Deterministic mock adapter for skill engine.
    Does not call foundation models or live document search.
    Maps evidence bundle observations to the six step fragile packing template.
    Preserves deliberate policy conflicts and source observation links.
    """

    def __init__(
        self,
        policyRetriever: Optional[PolicyRetriever] = None,
        modelCaller: Optional[ModelCaller] = None
    ) -> None:
        self.policyRetriever = policyRetriever or MockPolicyRetriever()
        self.modelCaller = modelCaller or MockModelCaller()

    def composeDraft(self, bundle: Dict[str, Any]) -> Dict[str, Any]:
        validBundle, bundleError = validateSchema("evidenceBundle", bundle)
        if not validBundle:
            raise ValueError(f"Invalid evidence bundle: {bundleError}")

        skillId = bundle["skillId"]
        observations = bundle["observations"]

        obsByAction: Dict[str, Dict[str, Any]] = {}
        for obs in observations:
            action = obs["candidateAction"]
            if action not in obsByAction:
                obsByAction[action] = obs

        citations = self.policyRetriever.retrievePolicyCitations(skillId)
        instructions = self.modelCaller.composeInstructions(observations)

        actionConfigs = [
            ("selectProduct", False),
            ("selectBox", False),
            ("addProtection", True),
            ("placeProduct", False),
            ("sealBox", False),
            ("attachLabel", True)
        ]

        steps: List[Dict[str, Any]] = []

        for index, (actionCode, checkpointRequired) in enumerate(actionConfigs):
            seq = index + 1
            obs = obsByAction.get(actionCode)
            instruction = instructions.get(actionCode, f"Execute step {seq}")

            if actionCode == "addProtection":
                policyStatus = "conflict"
                warning = "Demonstration shows single wrap but policy requires two layers"
            elif actionCode in citations:
                policyStatus = "supported"
                warning = None
            else:
                policyStatus = "supported" if obs else "needsReview"
                warning = None

            citation = citations.get(actionCode)

            steps.append({
                "stepId": f"step-00{seq}",
                "sequence": seq,
                "actionCode": actionCode,
                "instruction": instruction,
                "instructionHi": None,
                "sourceVideoId": obs["videoId"] if obs else None,
                "startMs": obs["startMs"] if obs else None,
                "endMs": obs["endMs"] if obs else None,
                "referenceFrameKey": obs["referenceFrameKey"] if obs else None,
                "confidence": obs["confidence"] if obs else None,
                "policyStatus": policyStatus,
                "policyCitation": citation,
                "warning": warning,
                "checkpointRequired": checkpointRequired,
                "audioKey": None,
                "evidenceObservationIds": [obs["observationId"]] if obs else []
            })

        if not validateActionOrder(steps):
            raise ValueError("Draft steps do not match the required six step template sequence")

        draft = {
            "schemaVersion": 1,
            "skillId": skillId,
            "title": "Pack fragile ceramic mug",
            "workflowType": "fragilePackingV1",
            "status": "reviewRequired",
            "version": 0,
            "materials": [
                "ceramic mug",
                "bubble wrap sheet",
                "corrugated box",
                "packing tape",
                "fragile label"
            ],
            "prerequisites": [
                "clean packing bench",
                "protective gloves"
            ],
            "steps": steps,
            "approvedBy": None,
            "approvedAt": None
        }

        validDraft, draftError = validateSchema("skillPackage", draft)
        if not validDraft:
            raise ValueError(f"Composed draft failed schema validation: {draftError}")

        return draft
