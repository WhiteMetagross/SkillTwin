import json
from typing import Any, Dict, List, Optional
from .modelCaller import LocalModelCaller, ModelCaller, ModelCompositionResult
from .observationMapper import TEMPLATE_ACTIONS

class BedrockModelCaller(ModelCaller):
    """
    Adapter invoking Amazon Bedrock foundation models to synthesize skill package instructions.
    Grounds instructions strictly in observed evidence and exact policy citations.
    Validates model JSON and falls back safely to deterministic local synthesis on failure.
    """

    def __init__(
        self,
        bedrockClient: Optional[Any] = None,
        modelId: str = "anthropic.claude-3-haiku-20240307-v1:0",
        fallbackCaller: Optional[ModelCaller] = None
    ) -> None:
        self.bedrockClient = bedrockClient
        self.modelId = modelId
        self.fallbackCaller = fallbackCaller or LocalModelCaller()

    def _getClient(self) -> Any:
        if self.bedrockClient is not None:
            return self.bedrockClient
        import boto3
        return boto3.client("bedrock-runtime")

    def composeSkillContent(
        self,
        skillId: str,
        observationsByAction: Dict[str, List[Dict[str, Any]]],
        citationsByAction: Dict[str, Optional[Dict[str, Any]]]
    ) -> ModelCompositionResult:
        try:
            client = self._getClient()
            prompt = self._formatPrompt(skillId, observationsByAction, citationsByAction)
            payload = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1024,
                "temperature": 0.0,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }

            response = client.invoke_model(
                modelId=self.modelId,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(payload)
            )

            rawBody = response["body"].read()
            parsedBody = json.loads(rawBody)

            contentBlocks = parsedBody.get("content", [])
            textOutput = ""
            for block in contentBlocks:
                if block.get("type") == "text":
                    textOutput += block.get("text", "")

            structured = json.loads(textOutput)
            return self._validateAndBuild(structured)
        except Exception:
            # Fallback safely to deterministic local path on malformed output or provider error
            return self.fallbackCaller.composeSkillContent(
                skillId,
                observationsByAction,
                citationsByAction
            )

    def _formatPrompt(
        self,
        skillId: str,
        observationsByAction: Dict[str, List[Dict[str, Any]]],
        citationsByAction: Dict[str, Optional[Dict[str, Any]]]
    ) -> str:
        # Include bounded observation evidence for each action slot
        obsEvidenceLines: List[str] = []
        for action in TEMPLATE_ACTIONS:
            obsList = observationsByAction.get(action, [])
            if obsList:
                actionsDesc = ", ".join([o.get("action", "") for o in obsList])
                objectsDesc = ", ".join(list({obj for o in obsList for obj in o.get("visibleObjects", [])}))
                obsEvidenceLines.append(f"- Slot '{action}': observed actions [{actionsDesc}], objects [{objectsDesc}]")
            else:
                obsEvidenceLines.append(f"- Slot '{action}': no video observations recorded")
        obsSummary = "\n".join(obsEvidenceLines)

        # Include exact policy citations for each action slot
        policyCitationLines: List[str] = []
        for action in TEMPLATE_ACTIONS:
            citation = citationsByAction.get(action)
            if citation:
                policyCitationLines.append(
                    f"- Slot '{action}': section '{citation.get('section')}', page {citation.get('page')}: \"{citation.get('excerpt')}\""
                )
            else:
                policyCitationLines.append(f"- Slot '{action}': no policy citation")
        citSummary = "\n".join(policyCitationLines)

        return (
            f"You are a SkillTwin packing instruction synthesiser for skill '{skillId}'.\n\n"
            f"Observed video evidence:\n{obsSummary}\n\n"
            f"Packaging policy requirements:\n{citSummary}\n\n"
            f"Synthesize instructions strictly conforming to this evidence. Return JSON with:\n"
            f"- title (string)\n"
            f"- materials (array of strings)\n"
            f"- prerequisites (array of strings)\n"
            f"- instructions (dictionary mapping each action code in {TEMPLATE_ACTIONS} to a concise sentence)"
        )

    def _validateAndBuild(self, data: Dict[str, Any]) -> ModelCompositionResult:
        title = data.get("title")
        materials = data.get("materials")
        prerequisites = data.get("prerequisites")
        instructions = data.get("instructions")

        if not isinstance(title, str) or not title:
            raise ValueError("Malformed title in model output")
        if not isinstance(materials, list) or not materials:
            raise ValueError("Malformed materials in model output")
        if not isinstance(prerequisites, list):
            raise ValueError("Malformed prerequisites in model output")
        if not isinstance(instructions, dict) or not instructions:
            raise ValueError("Malformed instructions in model output")

        # Validate that instructions map canonical actions to valid strings
        for action in TEMPLATE_ACTIONS:
            if action not in instructions or not isinstance(instructions[action], str) or not instructions[action]:
                raise ValueError(f"Missing or empty instruction for canonical action: {action}")

        return ModelCompositionResult(title, materials, prerequisites, instructions)
