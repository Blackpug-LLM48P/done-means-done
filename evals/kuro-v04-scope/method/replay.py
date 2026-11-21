#!/usr/bin/env python3
"""Replay eight retrieval conditions and three readers from the frozen study files."""

import argparse
import hashlib
import json
from pathlib import Path
import re

import scope_matcher
import score


ROOT = Path(__file__).resolve().parents[1]
READER_ARMS = ("one", "scope", "v04")
BASELINE = "source-veto"
CANDIDATE = "source_revision_action-rescue"


def machine_runs(cases):
    """Compute the shared rank order once and retain one audit per case/query."""
    predictions = {arm: {} for arm in score.DEFAULT_ARMS}
    audit = []
    for case in scope_matcher.evaluate(cases)["cases"]:
        cid = case["case_id"]
        for arm in predictions:
            predictions[arm][cid] = {}
        queries = []
        for q in case["queries"]:
            qid = q["id"]
            gates = q["arms"]
            first = gates["source"]["veto"]
            ranked = [
                {"row_id": row["row_id"], "bm25": row["bm25"],
                 "reasons": {gate: policies["veto"]["scores"][i]["reason"]
                             for gate, policies in gates.items()}}
                for i, row in enumerate(first["scores"])
            ]
            reasons = {}
            for gate, policies in gates.items():
                for policy, decision in policies.items():
                    arm = f"{gate}-{policy}"
                    predictions[arm][cid][qid] = decision["row_id"]
                    reasons[arm] = decision["reason"]
            queries.append({"id": qid, "target": q["target"],
                            "top_lexical_id": first["top_lexical_id"],
                            "ranked": ranked, "decision_reasons": reasons})
        audit.append({"case_id": cid, "rows": case["rows"], "queries": queries})
    return predictions, {"cases": audit}


def check_strata(strata, study):
    if not isinstance(strata, dict) or not strata:
        raise ValueError("strata: expected a nonempty object")
    assigned = set()
    for group, ids in strata.items():
        if not score.is_nonempty_string(group) or not isinstance(ids, list) or not ids:
            raise ValueError("strata: expected named strata with nonempty case ID lists")
        for cid in ids:
            if not isinstance(cid, str) or cid not in study or cid in assigned:
                raise ValueError(f"strata/{group}: invalid or repeated case {cid!r}")
            assigned.add(cid)
    if assigned != set(study):
        raise ValueError(f"strata: missing cases {sorted(set(study) - assigned)}")


def reader_runs(study, strata, sessions, root):
    raw = root / "results/raw"
    workflows = {"one": root / "design/one.txt", "scope": root / "design/scope.txt",
                 "v04": root.parents[1] / "skills/report-reality-check/SKILL.md"}
    check_strata(strata, study)
    if not isinstance(sessions, dict) or not sessions:
        raise ValueError("sessions: expected a nonempty object")
    names = {p.name for p in raw.glob("*.json")}
    if names != {f"{tag}.json" for tag in sessions}:
        raise ValueError("raw JSON filenames do not match registered sessions")

    seen = set()
    predictions = {f"reader-{arm}": {} for arm in READER_ARMS}
    for tag, meta in sessions.items():
        if not re.fullmatch(r"[A-Za-z0-9_-]+", tag):
            raise ValueError(f"invalid session tag {tag!r}")
        score.check_keys(meta, ("arm", "stratum", "files"), f"sessions/{tag}")
        arm, group = meta["arm"], meta["stratum"]
        if arm not in READER_ARMS or not isinstance(group, str) or group not in strata:
            raise ValueError(f"sessions/{tag}: unknown reader or stratum")
        if (arm, group) in seen:
            raise ValueError(f"sessions/{tag}: repeated reader/stratum")
        seen.add((arm, group))
        files = meta["files"]
        score.check_keys(files, ("cases.json", "workflow.txt", "reader.txt"), f"sessions/{tag}/files")
        if any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v)
               for v in files.values()):
            raise ValueError(f"sessions/{tag}/files: expected SHA-256 digests")
        formatted = json.dumps([study[cid] for cid in strata[group]], ensure_ascii=False, indent=2) + "\n"
        sources = {"cases.json": formatted.encode("utf-8"), "workflow.txt": workflows[arm].read_bytes(),
                   "reader.txt": (root / "design/reader.txt").read_bytes()}
        for name, content in sources.items():
            if hashlib.sha256(content).hexdigest() != files[name]:
                raise ValueError(f"{tag}/{name}: reconstructed packet differs from the frozen input")
        packet = score.read_json(raw / f"{tag}.json")
        score.check_keys(packet, strata[group], tag)
        for cid, answers in packet.items():
            qids = [q["id"] for q in study[cid]["queries"]]
            if "handoff" in qids:
                raise ValueError(f"{cid}: query ID collides with the handoff field")
            score.check_keys(answers, [*qids, "handoff"], f"{tag}/{cid}")
            if not score.is_nonempty_string(answers["handoff"]):
                raise ValueError(f"{tag}/{cid}: expected a nonempty handoff sentence")
            predictions[f"reader-{arm}"][cid] = {qid: answers[qid] for qid in qids}
    if seen != {(arm, group) for arm in READER_ARMS for group in strata}:
        raise ValueError("sessions: missing reader/stratum assignment")
    return predictions


def replay(root):
    inputs = root / "inputs"
    cases = score.read_json(inputs / "cases.json")
    study = score.index_records(cases, "case_id", "cases")
    for cid, case in study.items():
        score.index_records(case.get("rows"), "id", f"{cid}/rows", ("text", "source"), allow_empty=True)
        score.index_records(case.get("queries"), "id", f"{cid}/queries", ("question", "claim"))
    predictions, ranking = machine_runs(cases)
    predictions.update(reader_runs(study, score.read_json(inputs / "strata.json"),
                                   score.read_json(root / "design" / "sessions.json"), root))
    arms = [*score.DEFAULT_ARMS, *(f"reader-{a}" for a in READER_ARMS)]
    ballots = ["author", "independent"]
    if (inputs / "adjudicated-gold.json").exists():
        ballots.append("adjudicated")
    scores = {}
    for ballot in ballots:
        gold = score.read_json(inputs / f"{ballot}-gold.json")
        report = score.score(cases, gold, predictions, arms, BASELINE, CANDIDATE)
        for run in report["arms"].values():
            for case in run["by_case"].values():
                del case["questions"]
        del report["comparison"]["questions"]
        scores[ballot] = report
    return {"scores.json": scores, "predictions.json": predictions, "ranking.json": ranking}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="regenerate all three result files")
    mode.add_argument("--check", action="store_true", help="verify all three files byte-for-byte (default)")
    args = parser.parse_args()
    try:
        changed = []
        for name, data in replay(ROOT).items():
            path = ROOT / "results" / name
            payload = (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True,
                                  allow_nan=False) + "\n").encode("utf-8")
            if args.write:
                path.write_bytes(payload)
            elif not path.is_file() or path.read_bytes() != payload:
                changed.append(name)
        if changed:
            raise ValueError("missing or different results: " + ", ".join(changed))
    except (ValueError, OSError) as exc:
        parser.exit(1, f"replay: {exc}\n")
    print("Wrote all three result files." if args.write else "All three result files match.")


if __name__ == "__main__":
    main()
