import argparse
import json
import sys
from pathlib import Path
from .mockAdapter import MockSkillEngineAdapter

def main() -> None:
    parser = argparse.ArgumentParser(description="SkillTwin skill engine CLI mock")
    parser.add_argument("--bundle", required=True, help="Path to evidence bundle JSON file")
    parser.add_argument("--policy", required=False, help="Optional path to policy PDF or document")
    parser.add_argument("--output", required=False, help="Optional output JSON path")

    args = parser.parse_args()
    bundlePath = Path(args.bundle)

    if not bundlePath.is_file():
        print(f"Error: evidence bundle file not found at {bundlePath}", file=sys.stderr)
        sys.exit(1)

    with open(bundlePath, "r", encoding="utf-8") as f:
        bundle = json.load(f)

    customCitations = None
    if args.policy:
        policyPath = Path(args.policy)
        if not policyPath.is_file():
            print(f"Error: policy file not found at {policyPath}", file=sys.stderr)
            sys.exit(1)
        from .observationMapper import TEMPLATE_ACTIONS
        from .policyExtractor import PdfPolicyExtractor, PolicyIndex
        extractor = PdfPolicyExtractor()
        doc = extractor.extractDocument(policyPath.stem, policyPath.read_bytes())
        index = PolicyIndex()
        index.indexDocument(doc)
        customCitations = {action: index.findCitation(action) for action in TEMPLATE_ACTIONS}

    adapter = MockSkillEngineAdapter()
    try:
        draft = adapter.composeDraft(bundle, customCitations=customCitations)
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
