import argparse
import json
from pathlib import Path
import sys
from .mockAdapter import MockMediaIntelligenceAdapter
from .pipeline import processAssetManifest

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SkillTwin media intelligence local CLI"
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=("mock", "local"),
        help="Explicitly select deterministic fixture mocks or local media processing"
    )
    parser.add_argument("--manifest", required=True, help="Path to asset manifest JSON file")
    parser.add_argument("--asset-root", required=False, default=None, help="Root directory for local video assets")
    parser.add_argument("--output", required=False, default=None, help="Optional output JSON path")

    args = parser.parse_args()
    manifestPath = Path(args.manifest)

    if not manifestPath.is_file():
        print(f"Error: manifest file not found at {manifestPath}", file=sys.stderr)
        sys.exit(1)

    with open(manifestPath, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    try:
        if args.mode == "local":
            if not args.asset_root:
                parser.error("--asset-root is required when --mode local is selected")
            bundle = processAssetManifest(manifest, assetRoot=Path(args.asset_root))
        else:
            adapter = MockMediaIntelligenceAdapter()
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
