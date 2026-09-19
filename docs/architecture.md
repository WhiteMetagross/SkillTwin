# SkillTwin architecture

SkillTwin turns short demonstrations, images, and policy documents into an approved six step packing skill. The first workflow is fragilePackingV1.

## System boundaries and ownership

The architecture divides into three primary implementation areas communicating through frozen JSON Schema contracts.

1. Media intelligence
   - Service path: services/mediaIntelligence
   - Technology: Python 3.12 or higher
   - Responsibilities: Validates asset manifests, processes video files, detects speech segments, and extracts ordered observations with reference frame pointers

2. Skill engine and worker coach
   - Service paths: services/skillEngine and services/workerCoach
   - Technology: Python 3.12 or higher
   - Responsibilities: Aligns observations to the six step packing template, attaches policy citations, highlights visual policy conflicts, and evaluates worker checkpoint photos

3. Product platform
   - Service paths: services/api, services/pdfExport, apps/web, infrastructure
   - Technology: TypeScript, React, Node
   - Responsibilities: API gateway routing, job status tracking, supervisor review interface, approval transitions, and standard operating procedure PDF export

## Core data contracts

All inter service communication uses JSON Schema draft 2020 12 definitions located in packages/contracts/schemas.

1. assetManifest: Declares source videos, reference images, policy documents, and expected objects.
2. evidenceBundle: Records video metadata and ordered observations linked to candidate actions.
3. skillPackage: Defines the draft or approved skill with exactly six sequential steps, citations, and status.
4. checkpointRequest: Submits worker execution photo metadata for a given step and session.
5. checkpointResult: Returns the verification verdict (pass, fail, or uncertain) with confidence and corrections.
6. jobStatus: Tracks asynchronous analysis pipeline progress across named lifecycle stages.
7. errorResponse: Provides a consistent error envelope with safe machine readable error codes.

## The six step fragile packing template

The fragilePackingV1 workflow enforces six ordered action slots:

1. selectProduct
2. selectBox
3. addProtection
4. placeProduct
5. sealBox
6. attachLabel

If visual evidence is missing for a slot, the system marks the step as needsReview with null source fields. Model output alone cannot approve a skill. A human supervisor must explicitly review and approve the draft before publication.
