"""Reproduce the PR #15 execution inputs and original-text key from fixed PR #14 bytes."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess


STUDY = Path(__file__).resolve().parents[1]
REPO = STUDY.parents[1]
BASE = "82bf44e6a488c0d6e869c400d805453ce484e5f0"
PREVIOUS = "evals/kuro-v04-verifier-pairs/inputs"


def wire(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def read_fixed(name):
    data = subprocess.check_output(["git", "show", f"{BASE}:{PREVIOUS}/{name}"], cwd=REPO)
    return json.loads(data)


def materialize():
    rows = read_fixed("units.json")
    labels = {row["id"]: row for row in read_fixed("key.json")}
    if len(rows) != 16 or {row["id"] for row in rows} != labels.keys() or len(labels) != 16:
        raise ValueError("incomplete PR #14 controls")

    units, key, source_counts = {}, {}, Counter()
    for row in rows:
        case, body = row["case"], row["body"]
        family, source = (labels[row["id"]][name] for name in ("family", "source"))
        source_counts[family, source] += 1
        payload = {"case": case, "body": body}
        unit_id = "L-" + sha256(b"PR15\0" + wire(payload)).hexdigest()[:16]
        facts = [record["text"] for record in case["records"] if record["ref"] in ("E2", "E3")]
        if len(facts) != 2 or not body.endswith("".join(facts)):
            raise ValueError(f"{unit_id}: required facts do not match the fixed body")
        unit = {"id": unit_id, **payload}
        label = {"id": unit_id, "family": family, "source": source,
                 "needs_repair": source != "a", "facts": facts}
        if units.setdefault(unit_id, unit) != unit or key.setdefault(unit_id, label) != label:
            raise ValueError(f"{unit_id}: conflicting input or original-text key")

    expected = {(f"F{i}", src): count for i in range(1, 5)
                for src, count in (("ambiguous", 2), ("a", 1), ("b", 1))}
    if source_counts != expected or {(r["family"], r["source"]) for r in key.values()} != expected.keys() or len(units) != 12:
        raise ValueError("PR #14 controls do not reduce to four families with three inputs each")
    ids = sorted(units)
    return {"inputs/units.json": wire([units[uid] for uid in ids]),
            "inputs/key.json": wire([key[uid] for uid in ids])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "check"])
    args = parser.parse_args()
    data = materialize()
    frozen = {**data, "PROTOCOL.md": (STUDY / "PROTOCOL.md").read_bytes(),
              "method/materialize.py": Path(__file__).read_bytes()}
    data["inputs/freeze.sha256"] = "".join(
        f"{sha256(blob).hexdigest()}  {name}\n" for name, blob in sorted(frozen.items())
    ).encode()
    for name, blob in data.items():
        path = STUDY / name
        if args.action == "check" or path.exists():
            if path.read_bytes() != blob:
                raise ValueError(f"{name}: differs from frozen bytes")
        else:
            path.parent.mkdir(exist_ok=True, parents=True)
            with path.open("xb") as target:
                target.write(blob)
    print("12 fixed pairs, 4 normal and 8 needing repair; freeze verified")


if __name__ == "__main__":
    main()
