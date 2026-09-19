# Infrastructure definition and planned resources

This directory records planned cloud resources and configuration requirements for SkillTwin.

## Planned AWS services

1. Storage
   - Amazon S3 bucket for demonstration video uploads, reference images, policy documents, derived video frames, and exported PDF standard operating procedures

2. Compute and orchestration
   - AWS Step Functions state machine orchestrating media observation extraction, policy citation matching, and draft skill package generation
   - AWS Lambda functions executing lightweight transform jobs and API request handlers

3. Data persistence
   - Amazon DynamoDB tables for skill packages, job status tracking, and worker coaching session verification logs

4. Artificial intelligence services
   - Amazon Bedrock for foundation model instruction synthesis and multimodal analysis
   - Amazon Transcribe for spoken speech transcription on narrated video demonstrations
   - Amazon Textract for policy document layout and text extraction
   - Amazon Polly for Hindi audio narration synthesis

5. Security and distribution
   - AWS IAM role boundaries following least privilege principles
   - Amazon CloudWatch log groups for execution auditing and error tracing
