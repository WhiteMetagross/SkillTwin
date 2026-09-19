# Media intelligence service

This service accepts a validated asset manifest and produces a schema compliant evidence bundle for downstream skill composition.

## Capabilities and pipeline

The service provides both real media analysis and deterministic mock execution:

1. Asset manifest and video validation:
   - Validates manifest constraints (one to three videos)
   - Inspects video format, MIME type, decodability, and frame properties
   - Enforces the first release duration ceiling of 180 seconds per video

2. Storage adapters:
   - Local storage adapter resolving assets under a configured root directory
   - Amazon S3 storage adapter for cloud deployment

3. Frame sampling:
   - Samples representative video frames at regular intervals of roughly one to two seconds
   - Stores extracted JPEG frames using timestamp based keys:
     `skills/{skillId}/derived/frames/{videoId}/{timestampMs}.jpg`

4. Audio inspection and speech transcription:
   - Inspects audio tracks to verify whether usable speech is present
   - Silent or music only videos record `hasNarration: false` and `transcriptKey: null`
   - Spoken narration is transcribed with word and segment timestamps:
     `skills/{skillId}/derived/transcripts/{videoId}.json`
   - Spoken evidence is aligned to matching video observation intervals

5. Multimodal observation:
   - Evaluates frame sequences, transcript segments, and reference images
   - Constrains candidate actions strictly to the six canonical steps:
     `selectProduct`, `selectBox`, `addProtection`, `placeProduct`, `sealBox`, `attachLabel`
   - Emits before state, action, after state, visible objects, reference frame, and confidence
   - Never invents safety rules or unseen actions

6. Multi video bundle composition:
   - Merges observations from all videos in manifest order
   - Assigns unique global observation identifiers (`obs-001`, `obs-002`, ...)
   - Preserves independent per video timestamps and ordering
   - Validates complete bundle against `evidenceBundle.schema.json`

## CLI usage

### Mock mode for fixture contracts

```bash
python -m mediaIntelligence.cli --manifest ../../packages/contracts/fixtures/assetManifest.valid.json
```

### Real media mode with local assets

```bash
python -m mediaIntelligence.cli --manifest tests/assets/testManifestReal.json --asset-root tests/assets
```

## Additional documentation

- Central cloud requirements: [infrastructureRequirements.md](infrastructureRequirements.md)
- Video recording rules and boundaries: [recordingGuidance.md](recordingGuidance.md)
