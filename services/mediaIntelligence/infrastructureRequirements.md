# Media intelligence infrastructure requirements

This document specifies the AWS permissions, configuration settings, and resource quotas required by the media intelligence service for central infrastructure integration by Person 3.

## Service overview and AWS components

The media intelligence service requires access to three Amazon Web Services capabilities:

1. Amazon Simple Storage Service for storage of raw video uploads, extracted JPEG frames, and transcript JSON files
2. Amazon Transcribe for asynchronous speech recognition and word timestamp alignment
3. Amazon Bedrock for multimodal frame sequence observation and visual state reasoning
4. Amazon Rekognition as an optional service for label detection if requested in later phases

## Minimal IAM permissions

The execution role for media intelligence tasks must grant the following minimal actions:

### Amazon S3 permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "MediaStorageAccess",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:HeadObject"
      ],
      "Resource": [
        "arn:aws:s3:::skilltwin-media-*/*"
      ]
    }
  ]
}
```

### Amazon Transcribe permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TranscribeAccess",
      "Effect": "Allow",
      "Action": [
        "transcribe:StartTranscriptionJob",
        "transcribe:GetTranscriptionJob"
      ],
      "Resource": "*"
    }
  ]
}
```

### Amazon Bedrock permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockInvokeModel",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": [
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0"
      ]
    }
  ]
}
```

## Configuration parameters and environment variables

The following environment variables configure the media intelligence service:

| Variable | Purpose | Recommended value |
| --- | --- | --- |
| AWS_REGION | Target AWS region | ap-south-1 |
| S3_MEDIA_BUCKET | Primary bucket for source media and derived artifacts | skilltwin-media-storage |
| TRANSCRIBE_OUTPUT_BUCKET | Output bucket for transcript JSON files | skilltwin-media-storage |
| TRANSCRIBE_LANGUAGE_CODE | Primary language code for transcription | en-IN |
| BEDROCK_OBSERVER_MODEL_ID | Vision model for frame observation | anthropic.claude-3-5-sonnet-20240620-v1:0 |
| FRAME_SAMPLE_INTERVAL_MS | Milliseconds between sampled frame extractions | 1500 |
| VIDEO_MAX_DURATION_SECONDS | Hard ceiling for input video duration | 180 |

## Operational limits and quotas

1. Video duration limit:
   - Hard maximum of 180 seconds per video
   - Videos exceeding this limit must be rejected before sampling

2. Media file sizes and formats:
   - Supported MIME types: video/mp4, video/webm, video/quicktime
   - Maximum upload file size: 250 megabytes per video
   - Extracted JPEG frame quality: 85 percent compression to conserve bandwidth

3. Service timeouts:
   - Transcribe job completion timeout: 300 seconds
   - Bedrock frame observation timeout: 30 seconds
   - Frame sampling timeout per video: 20 seconds
