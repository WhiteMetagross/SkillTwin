from typing import Any, Dict, List, Optional
from .storage import LocalStorageAdapter, StorageAdapter
from .validator import validateSchema, validateTimestamps

class MockMediaIntelligenceAdapter:
    """
    Deterministic mock adapter for media intelligence.
    Does not process real video or extract real features.
    Provides deterministic fixture observations matching the six step fragile packing workflow.
    """

    def __init__(self, storageAdapter: Optional[StorageAdapter] = None) -> None:
        self.storageAdapter = storageAdapter or LocalStorageAdapter()

    def processManifest(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        valid, error = validateSchema("assetManifest", manifest)
        if not valid:
            raise ValueError(f"Invalid asset manifest: {error}")

        skillId = manifest["skillId"]
        videos = manifest["videos"]

        primaryVideoId = videos[0]["videoId"]
        evidenceVideos: List[Dict[str, Any]] = [
            {
                "videoId": primaryVideoId,
                "hasNarration": True,
                "transcriptKey": f"skills/{skillId}/derived/transcripts/{primaryVideoId}.json"
            }
        ]

        if len(videos) > 1:
            for extraVideo in videos[1:]:
                evidenceVideos.append({
                    "videoId": extraVideo["videoId"],
                    "hasNarration": False,
                    "transcriptKey": None
                })

        observations: List[Dict[str, Any]] = [
            {
                "observationId": "obs-001",
                "videoId": primaryVideoId,
                "startMs": 1000,
                "endMs": 4500,
                "beforeState": "shelf with mugs",
                "action": "inspect mug for defects",
                "afterState": "mug ready on bench",
                "visibleObjects": ["ceramic mug"],
                "spokenEvidence": "Inspect the mug for cracks first",
                "candidateAction": "selectProduct",
                "referenceFrameKey": f"skills/{skillId}/derived/frames/{primaryVideoId}/2000.jpg",
                "confidence": 0.95
            },
            {
                "observationId": "obs-002",
                "videoId": primaryVideoId,
                "startMs": 5000,
                "endMs": 8200,
                "beforeState": "flat boxes",
                "action": "assemble carton",
                "afterState": "assembled carton",
                "visibleObjects": ["cardboard box"],
                "spokenEvidence": "Choose the small standard box",
                "candidateAction": "selectBox",
                "referenceFrameKey": f"skills/{skillId}/derived/frames/{primaryVideoId}/6000.jpg",
                "confidence": 0.92
            },
            {
                "observationId": "obs-003",
                "videoId": primaryVideoId,
                "startMs": 9000,
                "endMs": 15500,
                "beforeState": "bare mug",
                "action": "wrap with bubble wrap",
                "afterState": "single wrapped mug",
                "visibleObjects": ["ceramic mug", "bubble wrap"],
                "spokenEvidence": "Wrap with bubble wrap",
                "candidateAction": "addProtection",
                "referenceFrameKey": f"skills/{skillId}/derived/frames/{primaryVideoId}/12000.jpg",
                "confidence": 0.88
            },
            {
                "observationId": "obs-004",
                "videoId": primaryVideoId,
                "startMs": 16000,
                "endMs": 20000,
                "beforeState": "open box",
                "action": "place mug in center",
                "afterState": "mug inside box",
                "visibleObjects": ["cardboard box", "bubble wrap"],
                "spokenEvidence": "Lower mug into the center",
                "candidateAction": "placeProduct",
                "referenceFrameKey": f"skills/{skillId}/derived/frames/{primaryVideoId}/18000.jpg",
                "confidence": 0.94
            },
            {
                "observationId": "obs-005",
                "videoId": primaryVideoId,
                "startMs": 21000,
                "endMs": 26000,
                "beforeState": "unsealed flaps",
                "action": "tape flaps",
                "afterState": "sealed box",
                "visibleObjects": ["cardboard box", "tape"],
                "spokenEvidence": "Apply tape along center and edge seams",
                "candidateAction": "sealBox",
                "referenceFrameKey": f"skills/{skillId}/derived/frames/{primaryVideoId}/23000.jpg",
                "confidence": 0.96
            },
            {
                "observationId": "obs-006",
                "videoId": primaryVideoId,
                "startMs": 27000,
                "endMs": 31000,
                "beforeState": "sealed box without label",
                "action": "attach fragile label",
                "afterState": "labeled box",
                "visibleObjects": ["cardboard box", "fragile label"],
                "spokenEvidence": "Stick the fragile label on top",
                "candidateAction": "attachLabel",
                "referenceFrameKey": f"skills/{skillId}/derived/frames/{primaryVideoId}/29000.jpg",
                "confidence": 0.98
            }
        ]

        for obs in observations:
            if not validateTimestamps(obs["startMs"], obs["endMs"]):
                raise ValueError(f"Invalid observation timestamps in {obs['observationId']}")

        bundle = {
            "schemaVersion": 1,
            "skillId": skillId,
            "videos": evidenceVideos,
            "observations": observations
        }

        validBundle, bundleError = validateSchema("evidenceBundle", bundle)
        if not validBundle:
            raise ValueError(f"Generated evidence bundle failed schema validation: {bundleError}")

        return bundle
