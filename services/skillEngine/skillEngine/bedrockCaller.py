import json
from typing import Any, Dict, List, Optional
from .modelCaller import LocalModelCaller, ModelCaller, ModelCompositionResult

class BedrockModelCaller(ModelCaller):
    """
    Adapter invoking Amazon Bedrock foundation models to synthesize skill package instructions.
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
        return (
            f"You are a SkillTwin packing instruction synthesiser. "
            f"Synthesize instructions for skill {skillId}. Return JSON with title, "
            f"materials (array of strings), prerequisites (array of strings), "
            f"and instructions (dictionary mapping action codes to concise instruction sentences)."
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

        return ModelCompositionResult(title, materials, prerequisites, instructions)
