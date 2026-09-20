# Skill engine service

This service accepts an evidence bundle and composes a six step draft skill package.

## Implementation details

The local CLI uses a deterministic adapter for fixture-driven development. The production CLI reads an evidence bundle and policy documents from private S3, extracts page-accurate policy text (using asynchronous Textract for scanned PDFs), invokes Amazon Bedrock without mock fallback, validates grounding, and writes a schema-valid version 0 draft back to S3.

Production requires `AWS_REGION`, `SKILLTWIN_BUCKET`, and `SKILL_ENGINE_MODEL_ID`:

```bash
skilltwin-skill-engine-production \
  --evidence-bundle-key skills/example/evidence/evidenceBundle.json \
  --policy-document-key skills/example/policies/warehouse-policy.pdf
```

Approved versions can be published through `PublicationService`. It computes a canonical SHA-256 hash of the untouched approved snapshot, validates every Hindi translation, stores and reads back every Polly MP3, writes a separate published snapshot, and commits the publication manifest last. Repeating the same approved content returns the verified existing manifest without invoking providers again.

## CLI usage

```bash
python -m skillEngine.cli --bundle ../../packages/contracts/fixtures/evidenceBundle.valid.json
```
