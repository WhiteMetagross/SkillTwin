# Media intelligence service

The service validates an asset manifest, stages bounded media, samples frames, detects speech across the complete video, and produces a schema-compatible evidence bundle. Shared JSON contracts remain unchanged.

## Runtime modes

Mode selection is mandatory in the CLI. Production never falls back to local or mock implementations.

Explicit deterministic contract mock:

```bash
python -m mediaIntelligence.cli --mode mock \
  --manifest ../../packages/contracts/fixtures/assetManifest.valid.json
```

Local media processing (requires FFmpeg, ffprobe, OpenCV, and Pillow):

```bash
python -m mediaIntelligence.cli --mode local \
  --manifest tests/assets/testManifestReal.json \
  --asset-root tests/assets
```

Production S3/Transcribe/Bedrock processing:

```bash
python -m mediaIntelligence.cli --mode production --manifest /work/assetManifest.json
```

Production validates configuration and binaries before creating the runtime. Provider errors and pending transcription jobs fail/defer explicitly; neither condition is represented as silence.

## Production configuration

Required:

| Variable | Purpose |
| --- | --- |
| `AWS_REGION` | Region used for all AWS clients |
| `S3_MEDIA_BUCKET` | Source and final derived artifact bucket |
| `BEDROCK_OBSERVER_MODEL_ID` | Multimodal observation model |

Optional controlled limits:

| Variable | Default |
| --- | --- |
| `TRANSCRIBE_OUTPUT_BUCKET` | `S3_MEDIA_BUCKET` |
| `FFMPEG_PATH`, `FFPROBE_PATH` | Executable discovered on `PATH` |
| `MEDIA_MAX_OBJECT_BYTES` | 262144000 (250 MiB maximum) |
| `MEDIA_MAX_STAGING_BYTES` | 786432000 (750 MiB maximum) |
| `FRAME_SAMPLE_INTERVAL_MS` | 1500 |
| `MEDIA_MAX_FRAMES` | 120 |

Manifest source keys must be owned by the skill and use these prefixes:

- `skills/{skillId}/source/videos/`
- `skills/{skillId}/source/images/`
- `skills/{skillId}/source/documents/`

## Transcribe lifecycle

`AmazonTranscribeService` exposes operations that can map directly to Step Functions tasks:

1. `startTranscription` starts a deterministic, idempotent job using the exact manifest source key.
2. `getTranscriptionStatus` returns `QUEUED`, `IN_PROGRESS`, `COMPLETED`, or `FAILED` and preserves provider/job identity.
3. `waitForTranscription` provides optional bounded polling for non-Step-Functions callers.
4. `completeTranscription` reads and validates the completed provider JSON, preserves language, words, segments, and timestamps, then writes `skills/{skillId}/derived/transcripts/{videoId}.json`.

`auto` maps to Amazon Transcribe language identification limited to `en-IN` and `hi-IN`; `enIN` and `hiIN` map to explicit `LanguageCode` values. Only a completed acoustic/provider determination can produce `hasNarration: false`.

## Container

Build from the repository root:

```bash
docker build -f services/mediaIntelligence/Dockerfile -t skilltwin-media .
docker run --rm skilltwin-media python tests/containerSmoke.py
```

Run production with AWS credentials supplied by the workload identity or normal SDK credential chain:

```bash
docker run --rm \
  -e AWS_REGION=ap-south-1 \
  -e S3_MEDIA_BUCKET=skilltwin-media-prod \
  -e BEDROCK_OBSERVER_MODEL_ID=your-model-id \
  skilltwin-media python -m mediaIntelligence.cli \
  --mode production --manifest /work/assetManifest.json
```

Mount `/work` when the manifest is provided from the host. Do not put credentials in the image or repository.

## Tests

```bash
pytest services/mediaIntelligence
```

Tests use deterministic SDK clients and require no AWS credentials. The container smoke test imports every runtime module and verifies FFmpeg/ffprobe availability.

See [infrastructureRequirements.md](infrastructureRequirements.md) for IAM and deployment requirements and [recordingGuidance.md](recordingGuidance.md) for input guidance.
