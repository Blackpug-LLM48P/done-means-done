"""Replay controlled proposals against frozen labels and compare within each source family."""
import argparse
from collections import Counter, defaultdict
from itertools import combinations
import json
from pathlib import Path
import subprocess
import sys

STUDY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STUDY.parents[1]))
from integrations.evidence_handoff import body_review, candidate_check, route


EXPECTED = {("ambiguous", "common"): "offer", ("ambiguous", "b"): "hold",
            ("a", "b"): "hold", ("b", "b"): "offer"}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def by_id(rows):
    require(isinstance(rows, list), "expected an array")
    index = {row["id"]: row for row in rows}
    require(len(index) == len(rows) and all(route.nonblank(uid) for uid in index), "duplicate or empty unit id")
    return index


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n").encode()


def family_inputs(family, cells, units):
    require(cells.keys() == EXPECTED.keys(), f"{family}: incomplete cell set")
    stimuli = {cell: units[uid] for cell, uid in cells.items()}
    require(len({u["body"] for u in stimuli.values()}) == 1, f"{family}: original body varies")
    require(stimuli["ambiguous", "common"]["case"] == stimuli["ambiguous", "b"]["case"],
            f"{family}: ambiguous pair must share its source")
    candidates = {}
    for cell, u in stimuli.items():
        trace = body_review.apply_review(u["case"], u["body"], u["r1_raw"])
        require(trace["status"] == "flagged" and trace["proposed_body"] != u["body"],
                f"{family}/{cell}: invalid controlled edit")
        candidates[cell] = trace["proposed_body"]
    require(len({candidates[s, "b"] for s in ("ambiguous", "a", "b")}) == 1,
            f"{family}: the B proposal varies across sources")
    require(candidates["ambiguous", "common"] != candidates["ambiguous", "b"],
            f"{family}: ambiguous alternatives coincide")

    sources = [stimuli[s, "b"]["case"] for s in ("ambiguous", "a", "b")]
    varying_rows = set()
    for left, right in combinations(sources, 2):
        require({k: v for k, v in left.items() if k != "records"} ==
                {k: v for k, v in right.items() if k != "records"}, f"{family}: case metadata differs")
        lr, rr = left["records"], right["records"]
        require(len(lr) == len(rr), f"{family}: differing record count")
        differing = [i for i, (a, b) in enumerate(zip(lr, rr)) if a != b]
        require(len(differing) == 1, f"{family}: expected exactly one changed source row")
        i = differing[0]
        require({k: v for k, v in lr[i].items() if k != "text"} ==
                {k: v for k, v in rr[i].items() if k != "text"}, f"{family}: row metadata differs")
        varying_rows.add(i)
    require(len(varying_rows) == 1, f"{family}: different relation rows were varied")

    # The physical row that changes must also reach the verifier's visible evidence packet.
    i = varying_rows.pop()
    for case in sources:
        observed = body_review.make_packet(case, stimuli["a", "b"]["body"])["records"]
        require(case["records"][i] in observed, f"{family}: varied source row not visible")


def event(unit, key, receipt):
    uid, cell = unit["id"], (key["source"], key["proposal"])
    expected = EXPECTED[cell]
    require(key["expected"] == expected, f"{uid}: invalid expected action for design cell")
    require(receipt["unit_id"] == uid and receipt["stage"] == "verify", f"{uid}: wrong receipt")
    transport = receipt["meta"]["status"]
    raw = receipt["raw"] if transport == "ok" else None
    trace = candidate_check.decide(unit["case"], unit["body"], unit["r1_raw"], raw,
                                   expected_prompt_sha256=receipt["prompt_sha256"])
    require(trace == receipt["trace"], f"{uid}: verifier replay differs")
    valid = (transport == "ok" and trace["error"] is None and trace["verdict"] in ("approve", "hold"))
    if valid:
        observed = {"approve": "offer", "hold": "hold"}[trace["verdict"]]
        require(trace["outcome"] == observed, f"{uid}: verifier action differs from its verdict")
    else:
        observed = "unclassified"
        require(trace["outcome"] == "hold", f"{uid}: a failed verifier offered a candidate")
    return dict(unit_id=uid, family=key["family"], source=cell[0], proposal=cell[1], expected=expected,
                observed=observed, valid=valid, correct=valid and expected == observed,
                transport=transport, validation_error=trace["error"], execution_outcome=trace["outcome"])


def counts(rows):
    den = Counter(r["expected"] for r in rows)
    return dict(cells=len(rows), expected_offers=den["offer"], expected_holds=den["hold"],
                valid_votes=sum(r["valid"] for r in rows), correct=sum(r["correct"] for r in rows),
                true_approvals=sum(r["observed"] == r["expected"] == "offer" for r in rows),
                true_holds=sum(r["observed"] == r["expected"] == "hold" for r in rows),
                false_approvals=sum(r["expected"] == "hold" and r["observed"] == "offer" for r in rows),
                false_holds=sum(r["expected"] == "offer" and r["observed"] == "hold" for r in rows),
                unclassified_ids=[r["unit_id"] for r in rows if not r["valid"]],
                failures=[r["unit_id"] for r in rows if not r["correct"]])


def replay():
    subprocess.run([sys.executable, "-B", STUDY / "method/materialize.py", "check"], check=True)
    units = by_id(route.read_json(STUDY / "inputs/units.json"))
    if units:
        subprocess.run([sys.executable, "-B", STUDY / "method/live.py", "--check"], check=True)
    keys = by_id(route.read_json(STUDY / "inputs/key.json"))
    receipts = STUDY / "results/live/receipts"
    require(units.keys() == keys.keys() == {p.stem for p in receipts.glob("*.json")},
            "units, keys and official receipts differ")
    families = defaultdict(dict)
    for uid, key in keys.items():
        cell, family = (key["source"], key["proposal"]), key["family"]
        require(route.nonblank(family) and cell in EXPECTED and cell not in families[family],
                f"{uid}: unsupported or duplicate family cell")
        families[family][cell] = uid
    require(len(families) <= 4, "more than four families")
    events, paired = [], []
    for family, cells in sorted(families.items()):
        family_inputs(family, cells, units)
        scores = {}
        for cell in EXPECTED:
            uid = cells[cell]
            row = event(units[uid], keys[uid], route.read_json(receipts / (uid + ".json")))
            events.append(row)
            scores[cell] = row["correct"]
        paired.append(dict(family=family, ambiguous_pair_correct=all(scores["ambiguous", p] for p in ("common", "b")),
                           b_across_sources_correct=all(scores[s, "b"] for s in ("ambiguous", "a", "b")),
                           all_four_correct=all(scores.values())))
    summary = counts(events)
    enough = len(families) == 4
    decision = ("insufficient_families" if not enough else
                "pass" if summary["correct"] == 16 else "hold")
    return {"events.json": events, "summary.json": dict(eligible_families=len(route.read_json(STUDY / "inputs/source-audit.json")["eligible"]), tested_families=len(families), planned_families=4,
            decision=decision, overall=summary, families=paired,
            ambiguous_pairs_correct=sum(r["ambiguous_pair_correct"] for r in paired),
            b_across_sources_correct=sum(r["b_across_sources_correct"] for r in paired),
            by_cell={f"{s}_{p}": counts([e for e in events if (e["source"], e["proposal"]) == (s, p)])
                     for s, p in EXPECTED})}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true")
    action.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, result in replay().items():
        path = STUDY / "results" / name
        if args.write:
            path.write_bytes(encoded(result))
        else:
            require(path.read_bytes() == encoded(result), f"{name}: result differs from replay")
    print("Verified controlled source and candidate contrasts, official votes, family comparisons and decision.")
