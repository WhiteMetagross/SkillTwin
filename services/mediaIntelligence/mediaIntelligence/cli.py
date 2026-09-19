import argparse
import json
from pathlib import Path
import sys
from .mockAdapter import MockMediaIntelligenceAdapter
from .pipeline import processAssetManifest

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SkillTwin media intelligence CLI with real media processing and fixture mock mode"
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

    # Determine processing mode based on asset root and file existence
    useRealPipeline = False
    assetRootPath = None

    if args.asset_root:
        assetRootPath = Path(args.asset_root)
        useRealPipeline = True
    else:
        # Check if first video sourceKey exists locally
        videos = manifest.get("videos", [])
        if videos:
            firstKey = videos[0].get("sourceKey", "")
            if Path(firstKey).is_file():
                useRealPipeline = True
                assetRootPath = Path.cwd()

    try:
        if useRealPipeline:
            bundle = processAssetManifest(manifest, assetRoot=assetRootPath)
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
