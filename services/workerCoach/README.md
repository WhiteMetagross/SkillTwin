# Worker coach service

This service evaluates worker checkpoint submissions and returns verification verdicts.

## Implementation details

The service uses a deterministic mock adapter that selects between pass, fail, and uncertain results based on explicit configuration. It does not perform live image recognition.

## CLI usage

```bash
python -m workerCoach.cli --request ../../packages/contracts/fixtures/checkpointRequest.valid.json --verdict pass
```
