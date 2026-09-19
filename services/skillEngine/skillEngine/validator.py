import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
import jsonschema

EXPECTED_ACTIONS = [
    "selectProduct",
    "selectBox",
    "addProtection",
    "placeProduct",
    "sealBox",
    "attachLabel"
]

def findSchemaPath(schemaName: str) -> Path:
    current = Path(__file__).resolve().parent
    candidates = [
        current.parent.parent.parent / "packages" / "contracts" / "schemas" / f"{schemaName}.schema.json",
        current.parent.parent / "packages" / "contracts" / "schemas" / f"{schemaName}.schema.json",
        Path.cwd() / "packages" / "contracts" / "schemas" / f"{schemaName}.schema.json"
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Schema not found for {schemaName}")

def validateSchema(schemaName: str, instance: Dict[str, Any]) -> Tuple[bool, str]:
    schemaPath = findSchemaPath(schemaName)
    with open(schemaPath, "r", encoding="utf-8") as f:
        schema = json.load(f)
    try:
        validator = jsonschema.Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(instance), key=lambda e: e.path)
        if errors:
            return False, ", ".join(err.message for err in errors)
        return True, ""
    except Exception as exc:
        return False, str(exc)

def validateActionOrder(steps: List[Dict[str, Any]]) -> bool:
    if len(steps) != 6:
        return False
    for index, step in enumerate(steps):
        if step.get("sequence") != index + 1:
            return False
        if step.get("actionCode") != EXPECTED_ACTIONS[index]:
            return False
    return True
