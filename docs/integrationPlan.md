# Integration plan

This document details the progressive integration pathway from Phase 0 skeleton to Phase 3 cloud deployment.

## Phase 0: Skeleton and frozen contracts (Current)

- Goal: Validate repository layout, frozen schemas, deterministic mock adapters, test suites, and web shell.
- Verification: All local test commands pass without AWS credentials. Schemas enforce strict boundary validation across Python and TypeScript.

## Phase 1: Independent cloud modules

- Goal: Replace mock adapters with real cloud provider integrations behind matching interfaces.
- Media intelligence: Connect Amazon Transcribe for speech and frame sampling algorithms.
- Skill engine: Connect Amazon Textract for policy PDF extraction and Amazon Bedrock for instruction composition.
- Worker coach: Connect multimodal Bedrock or Rekognition for worker checkpoint photo verification.
- Platform: Implement AWS Step Functions state machine orchestration and DynamoDB tables.

## Phase 2: End to end integration

- Goal: Pass recorded video and real policy documents through Step Functions to generate reviewable drafts.
- Verification: Successful pipeline execution without manual payload editing, verifying supervisor edit persistence into immutable version records.

## Phase 3: Deployment and verification

- Goal: Production deployment on AWS Amplify, API Gateway, Lambda, and S3.
- Verification: Multi station worker coaching on mobile devices with sub second checkpoint evaluations.
