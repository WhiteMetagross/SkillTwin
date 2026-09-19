from typing import Any, Dict, List, Optional, Set
from .observer import ALLOWED_CANDIDATE_ACTIONS, Observation
from .storage import StorageAdapter
from .validator import validateSchema, validateTimestamps

class BundleComposer:
    """
    Composes and validates the multi video evidence bundle.
    Preserves independent per video timestamps and ordering.
    Generates unique sequential observation identifiers across all videos.
    Enforces that observations reference valid supplied frames and interval boundaries.
    """

    def composeBundle(
        self,
        skillId: str,
        videoRecords: List[Dict[str, Any]],
        perVideoObservations: Dict[str, List[Observation]],
        storageAdapter: StorageAdapter,
        videoDurationMap: Optional[Dict[str, int]] = None,
        suppliedFrameKeysMap: Optional[Dict[str, Set[str]]] = None
    ) -> Dict[str, Any]:
        videoOrderMap = {v["videoId"]: index for index, v in enumerate(videoRecords)}
        allObservations: List[Observation] = []

        for videoId, obsList in perVideoObservations.items():
            if videoId not in videoOrderMap:
                raise ValueError(f"Observations reference unknown video ID: {videoId}")

            vRecord = next(v for v in videoRecords if v["videoId"] == videoId)
            isSilent = not vRecord.get("hasNarration", False)
            videoDuration = videoDurationMap.get(videoId) if videoDurationMap else None
            suppliedKeys = suppliedFrameKeysMap.get(videoId) if suppliedFrameKeysMap else None

            sortedInVideo = sorted(obsList, key=lambda o: (o.startMs, o.endMs))

            for obs in sortedInVideo:
                if not validateTimestamps(obs.startMs, obs.endMs):
                    raise ValueError(f"Invalid timestamp interval for video {videoId}: {obs.startMs}ms to {obs.endMs}ms")

                if videoDuration is not None and obs.endMs > videoDuration:
                    raise ValueError(
                        f"Observation interval {obs.startMs}ms-{obs.endMs}ms exceeds video duration of {videoDuration}ms"
                    )

                if obs.candidateAction not in ALLOWED_CANDIDATE_ACTIONS:
                    raise ValueError(f"Unsupported candidateAction in observation: {obs.candidateAction}")

                if obs.confidence < 0.0 or obs.confidence > 1.0:
                    raise ValueError(f"Observation confidence {obs.confidence} outside valid range 0.0 to 1.0")

                if suppliedKeys is not None and obs.referenceFrameKey not in suppliedKeys:
                    raise ValueError(
                        f"Observation reference frame '{obs.referenceFrameKey}' was not in supplied sampled frames"
                    )

                # Verify reference frame exists in storage
                if not storageAdapter.assetExists(obs.referenceFrameKey):
                    raise ValueError(f"Reference frame does not exist in storage: {obs.referenceFrameKey}")

                # Enforce silent video rule: spokenEvidence must be null
                if isSilent:
                    obs.spokenEvidence = None

                allObservations.append(obs)

        # Sort all observations by manifest video order first, then timestamp within video
        allObservations.sort(key=lambda o: (videoOrderMap[o.videoId], o.startMs))

        # Assign unique global observation IDs across all videos
        formattedObservations: List[Dict[str, Any]] = []
        for index, obs in enumerate(allObservations, start=1):
            obs.observationId = f"obs-{index:03d}"
            formattedObservations.append(obs.toDict())

        bundle = {
            "schemaVersion": 1,
            "skillId": skillId,
            "videos": videoRecords,
            "observations": formattedObservations
        }

        valid, error = validateSchema("evidenceBundle", bundle)
        if not valid:
            raise ValueError(f"Evidence bundle failed schema validation: {error}")

        return bundle
