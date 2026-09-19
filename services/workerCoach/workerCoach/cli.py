import argparse
import json
import sys
from pathlib import Path
from .mockAdapter import MockWorkerCoachAdapter

def main() -> None:
    parser = argparse.ArgumentParser(description="SkillTwin worker coach CLI")
    parser.add_argument("--request", required=True, help="Path to checkpoint request JSON file")
    parser.add_argument(
        "--verdict",
        choices=["pass", "fail", "uncertain"],
        default="pass",
        help="Explicit verdict selection for mock evaluation path"
    )
    parser.add_argument("--image", required=False, help="Optional path to real worker photo for content evaluation")
    parser.add_argument("--output", required=False, help="Optional output JSON path")

    args = parser.parse_args()
    reqPath = Path(args.request)

    if not reqPath.is_file():
        print(f"Error: request file not found at {reqPath}", file=sys.stderr)
        sys.exit(1)

    with open(reqPath, "r", encoding="utf-8") as f:
        request = json.load(f)

    adapter = MockWorkerCoachAdapter()
    try:
        if args.image:
            imagePath = Path(args.image)
            if not imagePath.is_file():
                print(f"Error: image file not found at {imagePath}", file=sys.stderr)
                sys.exit(1)
            imageBytes = imagePath.read_bytes()
            result = adapter.evaluateRequestContent(request, imageBytes=imageBytes)
        else:
            result = adapter.evaluateCheckpoint(request, verdict=args.verdict)
    except Exception as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        sys.exit(1)

    formatted = json.dumps(result, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(formatted)
        print(f"Checkpoint result written to {args.output}")
    else:
        print(formatted)

if __name__ == "__main__":
    main()
