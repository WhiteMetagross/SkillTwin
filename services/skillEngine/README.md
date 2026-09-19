# Skill engine service

This service accepts an evidence bundle and composes a six step draft skill package.

## Implementation details

The service uses a deterministic mock adapter that aligns observations to the six step template and flags policy citations and conflicts. It does not invoke live language models or PDF parsers. Pluggable interfaces allow future model calls and policy retrieval adapters.

## CLI usage

```bash
python -m skillEngine.cli --bundle ../../packages/contracts/fixtures/evidenceBundle.valid.json
```
