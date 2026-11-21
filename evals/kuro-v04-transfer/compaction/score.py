"""Score each frozen audit fact independently. Unknown and malformed values fail."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def score(raw, reference):
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None
    valid = isinstance(parsed, dict)
    rows = []
    for name, expected in reference.items():
        actual = parsed.get(name) if valid else None
        match = type(actual) is type(expected) and actual == expected
        rows.append({"fact": name, "expected": expected, "actual": actual, "pass": match})
    return {"json_object": valid, "score": sum(row["pass"] for row in rows), "total": len(rows), "facts": rows}


if __name__ == "__main__":
    public = json.loads((HERE / "observation.json").read_text())
    key = json.loads((HERE / "case.json").read_text())["frozen_answers"]
    results = {phase: score(public["model_outputs"][phase]["text"], key) for phase in ("after", "original")}
    print(json.dumps(results, indent=2))
