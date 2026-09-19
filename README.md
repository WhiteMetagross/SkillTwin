# SkillTwin

SkillTwin converts recorded work demonstrations, reference images, and policy documents into verified six step packing skills.

## Project overview

SkillTwin enforces the fragilePackingV1 workflow template. The pipeline coordinates three primary system areas:
1. Media intelligence: extracts observations and speech from video demonstrations.
2. Skill engine with worker coach: aligns observations to the six step template, checks policy adherence, and evaluates worker checkpoint photos.
3. Product platform: manages API routing, draft review, approval transitions, standard operating procedure PDF export, and worker guidance.

All components run locally using deterministic mock adapters and test fixtures with zero cloud credentials required.

## Repository layout

```text
SkillTwin/
  apps/
    web/                  React Vite TypeScript web application
  services/
    api/                  Express API service with mock endpoints
    mediaIntelligence/    Python service for video observation extraction
    skillEngine/          Python service for draft composition and policy checking
    workerCoach/          Python service for checkpoint verification
    pdfExport/            TypeScript service for standard operating procedure export
  packages/
    contracts/            Frozen JSON Schema definitions, fixtures, and validators
  infrastructure/         Planned AWS resources and configuration templates
  docs/                   Architecture, decisions, and integration roadmap
  .github/workflows/      Continuous integration workflow
```

## Quick start

### Prerequisites

- Node.js version 20 or higher
- Python version 3.12 or higher

### 1. Install dependencies

Install Node workspace packages from the repository root:

```bash
npm install
```

Install Python service dependencies:

```bash
pip install jsonschema pytest
```

### 2. Validate contract fixtures

Validate all JSON fixtures against their draft 2020 12 schemas and semantic rules:

```bash
npm run validate:fixtures
```

### 3. Run automated tests

Run all TypeScript test suites:

```bash
npm run test:contracts
npm run test:api
npm run test:pdf
```

Run all Python service test suites:

```bash
pytest services/mediaIntelligence
pytest services/skillEngine
pytest services/workerCoach
```

### 4. Build TypeScript packages

Compile contracts, services, and web application:

```bash
npm run build
```

### 5. Start the web application

Run the local development server:

```bash
npm run dev:web
```

Open `http://localhost:3000` in your web browser to explore:
- Dashboard: overview of skills and the six step pipeline
- Upload: demonstration video and policy document submission
- Processing: pipeline execution progress across stages
- Review: supervisor review showing the deliberate policy conflict on step 3 with full document citations
- Published Skill: approved standard operating procedure with English and Hindi instructions
- Guided Mode: interactive worker coaching interface with camera checkpoint simulation
- Completion Report: verification summary report

### 6. Exercise Python service CLI entry points

Media intelligence service:

```bash
python -m mediaIntelligence.cli --manifest ../../packages/contracts/fixtures/assetManifest.valid.json
```
(Run from `services/mediaIntelligence`)

Skill engine service:

```bash
python -m skillEngine.cli --bundle ../../packages/contracts/fixtures/evidenceBundle.valid.json
```
(Run from `services/skillEngine`)

Worker coach service:

```bash
python -m workerCoach.cli --request ../../packages/contracts/fixtures/checkpointRequest.valid.json --verdict pass
python -m workerCoach.cli --request ../../packages/contracts/fixtures/checkpointRequest.valid.json --verdict fail
python -m workerCoach.cli --request ../../packages/contracts/fixtures/checkpointRequest.valid.json --verdict uncertain
```
(Run from `services/workerCoach`)
