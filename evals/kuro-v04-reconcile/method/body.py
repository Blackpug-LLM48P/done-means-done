"""Mask shared handoffs for two readers, preserve independent votes and resolve disputed flags."""
import argparse
import json
import secrets
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
RESULTS = STUDY / "results"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")


def packet(work):
    cases = {c["case_id"]: c for c in read(STUDY / "inputs/cases.json")}
    gold = read(STUDY / "inputs/gold.json")
    runs = read(RESULTS / "runs.json")
    if len(runs) != 16 or len(cases) != 8:
        raise ValueError("expected 16 returns from 8 cases")
    path = RESULTS / "labels.json"
    units = {(r["session_id"], r["case_id"]) for r in runs}
    if not path.exists():
        labels = {"H-" + secrets.token_hex(12): {"session_id": s, "case_id": c}
                  for s, c in sorted(units)}
        with path.open("x", encoding="utf-8") as output:
            json.dump(labels, output, ensure_ascii=False, indent=2, sort_keys=True)
            output.write("\n")
    labels = read(path)
    by_unit = {(r["session_id"], r["case_id"]): k for k, r in labels.items()}
    if len(units) != 16 or by_unit.keys() != units:
        raise ValueError("label mapping does not cover the observed returns")
    rows = []
    for r in runs:
        cid = r["case_id"]
        log = read(STUDY / r["receiver_file"])
        if log["B0"]["handoff"] != log["B1"]["handoff"]:
            raise ValueError("body changed between receivers")
        rows.append({"label": by_unit[r["session_id"], cid], "case": cases[cid],
                     "facts": gold[cid]["facts"], "handoff": log["B0"]["handoff"]})
    work.mkdir(exist_ok=True, parents=True)
    save(work / "packet.json", sorted(rows, key=lambda row: row["label"]))


def ballots(work, finalize):
    rows = {row["label"]: row for row in read(work / "packet.json")}
    a, b = (read(work / (name + ".json")) for name in ("first", "second"))
    if set(rows) != set(a) or set(a) != set(b):
        raise ValueError("vote coverage differs")
    for vote in (a, b):
        for k, v in vote.items():
            if (set(v) != {"facts", "extra", "notes"} or not isinstance(v["facts"], list)
                    or len(v["facts"]) != len(rows[k]["facts"]) or
                    not all(type(f) is bool for f in [*v["facts"], v["extra"]])
                    or not isinstance(v["notes"], str)):
                raise ValueError("invalid vote " + k)
    discrepancies = {}
    for k in a:
        indices = [i for i, (x, y) in enumerate(zip(a[k]["facts"], b[k]["facts"])) if x != y]
        extra = a[k]["extra"] != b[k]["extra"]
        if indices or extra:
            discrepancies[k] = {"fact_indices": indices, "extra_disagreement": extra}
    save(work / "disputes.json", [{**rows[k], "dispute": d, "first": a[k], "second": b[k]}
                                 for k, d in sorted(discrepancies.items())])
    print("disputed returns:", len(discrepancies))
    if not finalize:
        return
    third = read(work / "third.json") if discrepancies else {}
    if third.keys() != discrepancies.keys():
        raise ValueError("third vote must cover just the disputed rows")
    final = dict(a)
    for k, v in third.items():
        if len(v["facts"]) != len(a[k]["facts"]) or not v["notes"] or not all(
                type(f) is bool for f in [*v["facts"], v["extra"]]):
            raise ValueError("invalid arbitration")
        if any(xx == yy != zz for xx, yy, zz in zip([*a[k]["facts"], a[k]["extra"]],
                [*b[k]["facts"], b[k]["extra"]], [*v["facts"], v["extra"]])):
            raise ValueError("arbitration changed an agreed flag")
        final[k] = v
    for name, data in (("body-vote-1", a), ("body-vote-2", b), ("body-ballot", final),
                       ("body-adjudication", {"double_graded": len(a), "disagreements": discrepancies,
                                              "third_ballot": third})):
        save(RESULTS / (name + ".json"), data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["packet", "disputes", "finalize"])
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    if args.command == "packet":
        packet(args.work)
    else:
        ballots(args.work, args.command == "finalize")
