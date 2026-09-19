import argparse
import json
import sys
from pathlib import Path
from .mockAdapter import MockMediaIntelligenceAdapter

def main() -> None:
    parser = argparse.ArgumentParser(description="SkillTwin media intelligence CLI mock")
    parser.add_argument("--manifest", required=True, help="Path to asset manifest JSON file")
    parser.add_argument("--output", required=False, help="Optional output JSON path")

    args = parser.parse_args()
    manifestPath = Path(args.manifest)

    if not manifestPath.is_file():
        print(f"Error: manifest file not found at {manifestPath}", file=sys.stderr)
        sys.exit(1)

    with open(manifestPath, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    adapter = MockMediaIntelligenceAdapter()
    try:
        bundle = adapter.processManifest(manifest)
    except Exception as exc:
        print(f"Processing failed: {exc}", file=sys.stderr)
        sys.exit(1)

    formatted = json.dumps(bundle, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(formatted)
        print(f"Evidence bundle written to {args.output}")
    else:
        print(formatted)

if __name__ == "__main__":
    main()
