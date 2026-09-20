# Media intelligence infrastructure requirements

## Runtime resources

The production container requires:

- Python 3.12
- FFmpeg and ffprobe
- writable temporary disk for bounded S3 staging (750 MiB by default)
- network access to Amazon S3, Amazon Transcribe, and the configured Amazon Bedrock Runtime model

Source videos are limited to 180 seconds, 250 MiB, 4096 x 2160, 120 frames per second, and 120 sampled frames. Actual streamed bytes are checked against both S3 metadata and configured limits. Reference images are limited to 10 MiB and 32 megapixels. Media is validated before Transcribe or Bedrock calls.

## IAM permissions

Scope bucket resources and the Bedrock model ARN to the deployed environment.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "MediaObjectReadWrite",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": [
        "arn:aws:s3:::skilltwin-media-*/*"
      ]
    },
    {
      "Sid": "TranscriptionLifecycle",
      "Effect": "Allow",
      "Action": [
        "transcribe:StartTranscriptionJob",
        "transcribe:GetTranscriptionJob"
      ],
      "Resource": "*"
    },
    {
      "Sid": "BedrockObservation",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel"],
      "Resource": "arn:aws:bedrock:*::foundation-model/*"
    }
  ]
}
```

`HeadObject` authorization is evaluated through `s3:GetObject`. If `TRANSCRIBE_OUTPUT_BUCKET` differs from `S3_MEDIA_BUCKET`, grant the same object permissions on both buckets and configure Amazon Transcribe to write to the output bucket.

Amazon Transcribe also needs permission to read the exact source object and write its raw result. Prefer an execution role and bucket policies; never inject long-lived credentials into the image.

## Environment

Required at startup:

- `AWS_REGION`
- `S3_MEDIA_BUCKET`
- `BEDROCK_OBSERVER_MODEL_ID`
- resolvable `ffmpeg` and `ffprobe` executables (or `FFMPEG_PATH` and `FFPROBE_PATH`)

Optional:

- `TRANSCRIBE_OUTPUT_BUCKET`
- `MEDIA_MAX_OBJECT_BYTES` (cannot exceed 250 MiB)
- `MEDIA_MAX_STAGING_BYTES`
- `FRAME_SAMPLE_INTERVAL_MS`
- `MEDIA_MAX_FRAMES` (cannot exceed 120)

Missing or invalid production configuration stops startup. There is no mock or local fallback.

## Orchestration

Use separate Step Functions tasks for start, wait/status, and completion:

```text
Validate and stage media -> startTranscription
                         -> Wait -> getTranscriptionStatus
                                   | queued/in progress -> Wait
                                   | failed -> fail job
                                   | completed -> completeTranscription
                                               -> persist final transcript artifact
```

Persist the serialized job identity between tasks. Retries use a deterministic job name derived from skill ID, video ID, and the real source key. Access denial, throttling, provider failure, pending, and timeout are distinct errors and must use the workflow's appropriate fail or retry policy.

## Verification

Offline:

```bash
pytest services/mediaIntelligence
docker build -f services/mediaIntelligence/Dockerfile -t skilltwin-media .
docker run --rm skilltwin-media python tests/containerSmoke.py
```

Live cloud proof additionally requires valid credentials, a test bucket containing a real uploaded media object, Transcribe access, and Bedrock model access. Offline mocked-SDK tests do not constitute live AWS validation.
