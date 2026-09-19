# Media intelligence service

This service accepts an asset manifest and produces an evidence bundle.

## Implementation details

The service uses a deterministic mock adapter that returns fixture based observations and evidence. It does not perform live computer vision or media analysis. Storage interfaces allow future adapters for local disk and cloud storage.

## CLI usage

```bash
python -m mediaIntelligence.cli --manifest ../../packages/contracts/fixtures/assetManifest.valid.json
```
