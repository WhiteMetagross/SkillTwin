import argparse
import json
from pathlib import Path
import sys

from .mockAdapter import MockMediaIntelligenceAdapter
from .pipeline import processAssetManifest
from .runtime import createProductionRuntime


def main() -> None:
    parser = argparse.ArgumentParser(description="SkillTwin media intelligence runtime")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["production", "local", "mock"],
        help="Explicit runtime mode; production never falls back to local or mock adapters",
    )
    parser.add_argument("--manifest", required=True, help="Path to asset manifest JSON file")
    parser.add_argument("--asset-root", help="Required root directory for local media mode")
    parser.add_argument("--output", help="Optional output JSON path")
    args = parser.parse_args()

    manifestPath = Path(args.manifest)
    if not manifestPath.is_file():
        print(f"Error: manifest file not found at {manifestPath}", file=sys.stderr)
        sys.exit(1)
    try:
        manifest = json.loads(manifestPath.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error: could not read manifest: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        if args.mode == "production":
            if args.asset_root:
                raise ValueError("--asset-root is not valid in production mode")
            bundle = createProductionRuntime().processManifest(manifest)
        elif args.mode == "local":
            if not args.asset_root:
                raise ValueError("--asset-root is required in local mode")
            bundle = processAssetManifest(manifest, assetRoot=Path(args.asset_root))
        else:
            if args.asset_root:
                raise ValueError("--asset-root is not valid in mock mode")
            bundle = MockMediaIntelligenceAdapter().processManifest(manifest)
    except Exception as exc:
        print(f"Processing failed in {args.mode} mode: {exc}", file=sys.stderr)
        sys.exit(1)

    formatted = json.dumps(bundle, indent=2)
    if args.output:
        Path(args.output).write_text(formatted, encoding="utf-8")
        print(f"Evidence bundle written to {args.output}")
    else:
        print(formatted)


if __name__ == "__main__":
    main()
