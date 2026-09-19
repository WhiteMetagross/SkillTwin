# Skill engine and worker coach infrastructure requirements

This document specifies the AWS permissions, configuration settings, and resource quotas required by the skill engine and worker coach services for central infrastructure integration by Person 3.

## Service overview and AWS components

The skill engine and worker coach require access to four Amazon Web Services capabilities:

1. Amazon Bedrock for foundation model instruction synthesis and multimodal checkpoint evaluation
2. Amazon Textract for policy text extraction from scanned packaging documents
3. Amazon Translate for translation of approved English steps into Hindi
4. Amazon Polly for neural audio narration synthesis of approved instructions

## Minimal IAM permissions

The execution role for skill engine and worker coach tasks must grant the following minimal actions:

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
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-haiku-20240307-v1:0",
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0"
      ]
    }
  ]
}
```

### Amazon Textract permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TextractDetectDocumentText",
      "Effect": "Allow",
      "Action": [
        "textract:DetectDocumentText"
      ],
      "Resource": "*"
    }
  ]
}
```

### Amazon Translate permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TranslateText",
      "Effect": "Allow",
      "Action": [
        "translate:TranslateText"
      ],
      "Resource": "*"
    }
  ]
}
```

### Amazon Polly permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PollySynthesizeSpeech",
      "Effect": "Allow",
      "Action": [
        "polly:SynthesizeSpeech"
      ],
      "Resource": "*"
    }
  ]
}
```

## Configuration parameters and environment variables

The following environment variables configure the service providers:

| Variable | Purpose | Recommended value |
| --- | --- | --- |
| AWS_REGION | Target AWS region | ap-south-1 |
| BEDROCK_MODEL_ID | Foundation model identifier | anthropic.claude-3-haiku-20240307-v1:0 |
| BEDROCK_VISION_MODEL_ID | Vision model identifier | anthropic.claude-3-5-sonnet-20240620-v1:0 |
| POLLY_VOICE_HI | Neural voice for Hindi audio | Aditi |
| POLLY_VOICE_EN | Neural voice for English audio | Kajal |
| TEXTRACT_MAX_BYTES | Document size ceiling | 5242880 |

## Operational limits and quotas

1. Bedrock inference timeouts:
   - Instruction composition timeout limit: 15 seconds
   - Checkpoint vision verification timeout limit: 10 seconds

2. Payload size constraints:
   - Textract synchronous document buffer limit: 5 megabytes
   - Polly character limit per request: 3000 characters
   - Checkpoint photo input limit: 4 megabytes
