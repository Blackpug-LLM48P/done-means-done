"""Check the manual control commitment and combine the preregistered, separately scored gates."""
import argparse
import hashlib
import json
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((STUDY / name).read_bytes())


def decide():
    controls = read("inputs/control-gold.json")
    canonical = json.dumps(controls, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    seal_bytes = (STUDY / "design/sealed/controls.json").read_bytes()
    hashes = read("design/sealed.json")["controls"]
    if (hashlib.sha256(seal_bytes).hexdigest() != hashes["ciphertext_sha256"]
            or hashlib.sha256(canonical).hexdigest() != hashes["plaintext_sha256"]
            or json.loads(seal_bytes)["digest"] != hashes["plaintext_sha256"]):
        raise ValueError("control commitment differs from the independent manual ballot")
    natural = read("results/natural-summary.json")
    fault = read("results/control-scores.json")
    history = {k: v for k, v in fault["by_receipt"].items() if k.startswith("M3V7-")}
    restored = {k: v["recovered"] for k, v in history.items()}
    gates = {"historical_delivery": len(restored) == 2 and all(v == ["advance_operation"] for v in restored.values()),
             "independent": natural["modes"]["independent"]["passes_natural"],
             "continuous": natural["modes"]["continuous"]["passes_natural"],
             "manual_receipt_expectations": fault["all_expectations_met"]}
    return {"decision": "adopt" if all(gates.values()) else "hold", "gates": gates,
            "historical_recovered": restored,
            "scope": "Single dry-run receiver using the frozen PR 9 caller and DMD v0.4."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--write", action="store_true")
    options.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = decide()
    file = STUDY / "results/decision.json"
    content = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    if args.write:
        file.write_bytes(content)
    elif content != file.read_bytes():
        raise SystemExit("saved decision differs")
    print(result["decision"], result["gates"])
