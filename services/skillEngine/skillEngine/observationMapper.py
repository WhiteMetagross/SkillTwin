from typing import Any, Dict, List, Optional

TEMPLATE_ACTIONS = [
    "selectProduct",
    "selectBox",
    "addProtection",
    "placeProduct",
    "sealBox",
    "attachLabel"
]

class ActionEvidence:
    def __init__(
        self,
        actionCode: str,
        observations: List[Dict[str, Any]],
        representative: Optional[Dict[str, Any]]
    ) -> None:
        self.actionCode = actionCode
        self.observations = observations
        self.representative = representative

    @property
    def observationIds(self) -> List[str]:
        return [obs["observationId"] for obs in self.observations]

    @property
    def hasEvidence(self) -> bool:
        return self.representative is not None

def selectRepresentativeObservation(observations: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not observations:
        return None
    # Quality rule: select observation with highest confidence, breaking ties by longest duration
    bestObs = observations[0]
    for obs in observations[1:]:
        obsConf = obs.get("confidence", 0.0)
        bestConf = bestObs.get("confidence", 0.0)
        if obsConf > bestConf:
            bestObs = obs
        elif obsConf == bestConf:
            obsDuration = obs.get("endMs", 0) - obs.get("startMs", 0)
            bestDuration = bestObs.get("endMs", 0) - bestObs.get("startMs", 0)
            if obsDuration > bestDuration:
                bestObs = obs
    return bestObs

def mapObservationsToActionSlots(
    observations: List[Dict[str, Any]]
) -> List[ActionEvidence]:
    grouped: Dict[str, List[Dict[str, Any]]] = {action: [] for action in TEMPLATE_ACTIONS}
    for obs in observations:
        action = obs.get("candidateAction")
        if action in grouped:
            grouped[action].append(obs)

    result: List[ActionEvidence] = []
    for action in TEMPLATE_ACTIONS:
        obsList = grouped[action]
        representative = selectRepresentativeObservation(obsList)
        result.append(ActionEvidence(action, obsList, representative))
    return result
