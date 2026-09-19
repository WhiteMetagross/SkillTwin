import argparse
import json
import sys
from pathlib import Path
from .mockAdapter import MockSkillEngineAdapter

def main() -> None:
    parser = argparse.ArgumentParser(description="SkillTwin skill engine CLI mock")
    parser.add_argument("--bundle", required=True, help="Path to evidence bundle JSON file")
    parser.add_argument("--output", required=False, help="Optional output JSON path")

    args = parser.parse_args()
    bundlePath = Path(args.bundle)

    if not bundlePath.is_file():
        print(f"Error: evidence bundle file not found at {bundlePath}", file=sys.stderr)
        sys.exit(1)

    with open(bundlePath, "r", encoding="utf-8") as f:
        bundle = json.load(f)

    adapter = MockSkillEngineAdapter()
    try:
        draft = adapter.composeDraft(bundle)
    except Exception as exc:
        print(f"Draft composition failed: {exc}", file=sys.stderr)
        sys.exit(1)

    formatted = json.dumps(draft, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(formatted)
        print(f"Skill draft written to {args.output}")
    else:
        print(formatted)

if __name__ == "__main__":
    main()
