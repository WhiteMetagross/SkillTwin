from typing import Any, Dict, List, Optional

class ModelCompositionResult:
    def __init__(
        self,
        title: str,
        materials: List[str],
        prerequisites: List[str],
        instructions: Dict[str, str]
    ) -> None:
        self.title = title
        self.materials = materials
        self.prerequisites = prerequisites
        self.instructions = instructions

class ModelCaller:
    def composeSkillContent(
        self,
        skillId: str,
        observationsByAction: Dict[str, List[Dict[str, Any]]],
        citationsByAction: Dict[str, Optional[Dict[str, Any]]]
    ) -> ModelCompositionResult:
        raise NotImplementedError("Subclasses must implement composeSkillContent")

class LocalModelCaller(ModelCaller):
    """
    Deterministic local instruction composer.
    Derives title, materials, prerequisites, and instructions directly from observed actions
    and visible objects rather than returning static text.
    """

    def composeSkillContent(
        self,
        skillId: str,
        observationsByAction: Dict[str, List[Dict[str, Any]]],
        citationsByAction: Dict[str, Optional[Dict[str, Any]]]
    ) -> ModelCompositionResult:
        allVisibleObjects: List[str] = []
        for obsList in observationsByAction.values():
            for obs in obsList:
                for item in obs.get("visibleObjects", []):
                    if item not in allVisibleObjects:
                        allVisibleObjects.append(item)

        # Infer target item name
        targetItem = "fragile item"
        for candidate in ["ceramic mug", "glass bottle", "porcelain vase"]:
            if candidate in allVisibleObjects:
                targetItem = candidate
                break

        title = f"Pack {targetItem}"

        # Materials derived from visible objects
        materials: List[str] = []
        materialKeywords = ["mug", "box", "wrap", "tape", "label", "carton", "sheet"]
        for obj in allVisibleObjects:
            if any(kw in obj.lower() for kw in materialKeywords) and obj not in materials:
                materials.append(obj)
        if not materials:
            materials = ["cardboard box", "packing tape", "protective cushioning"]

        prerequisites = ["clean packing bench", "protective gloves"]

        instructions: Dict[str, str] = {}
        for actionCode, obsList in observationsByAction.items():
            if obsList:
                rep = obsList[0]
                actionDesc = rep.get("action", "")
                spoken = rep.get("spokenEvidence")
                if actionCode == "selectProduct":
                    instructions[actionCode] = f"Inspect the {targetItem} for surface cracks and defects."
                elif actionCode == "selectBox":
                    instructions[actionCode] = "Assemble the standard corrugated carton."
                elif actionCode == "addProtection":
                    instructions[actionCode] = f"Wrap the {targetItem} completely with bubble wrap cushioning."
                elif actionCode == "placeProduct":
                    instructions[actionCode] = f"Place the wrapped {targetItem} upright in the center of the box."
                elif actionCode == "sealBox":
                    instructions[actionCode] = "Close box flaps and seal center seam and edges using H tape method."
                elif actionCode == "attachLabel":
                    instructions[actionCode] = "Affix fragile shipping label visibly on the top face of the sealed box."
                else:
                    instructions[actionCode] = actionDesc or f"Execute {actionCode}"
            else:
                instructions[actionCode] = f"Perform required action {actionCode} according to station guidelines."

        return ModelCompositionResult(title, materials, prerequisites, instructions)
