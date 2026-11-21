"""Replay the explicit-referent controls against their development ledgers.

The handoff parser covers the published wording. An unrecognized sentence
requires review and is never counted as a pass. No holdout data is read.
"""
import argparse
import json
import re
import runpy
from pathlib import Path


TARGET_INSTRUCTIONS = {
    "audit": "この回答の state は、締め時刻時点の件数と必要な荷番を正しく照合して、この報告を作成できたかを表します。",
    "delivery": "この回答の state は、締め時刻までに対象便の配達が全件完了したかを表します。",
}
ITEM = r"L[0-9A-F]{6}"
DETAIL = rf"({ITEM})(?:（(保留|取消|証跡なし)）)?"
HANDOFF = re.compile(
    r"(?P<cutoff>\d{2}:\d{2})時点(?:で、?|の(?:正式な配達証跡を照合しました。)?)"
    r"対象(?P<total>\d+)件のうち、?(?:配達)?完了(?:は)?(?P<complete>\d+)件、"
    r"未完了(?:は)?(?P<pending>\d+)件です。"
    rf"(?:未完了の正式荷番は(?P<items>{DETAIL}(?:、{DETAIL})*)です。)?"
)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def ledger_facts(packet, oracle):
    cutoff = re.search(r"同日 (\d{2}:\d{2}) 時点", packet["request"])[1]
    rows = [s.split("|") for s in packet["records"]]
    roster = {i for row in rows if row[0] == "M" for i in row[1].split(",")}
    aliases = {(r[1], r[2]): r[3] for r in rows if r[0] == "A"}
    latest = {}
    proofs = {}
    for row in rows:
        if row[0] != "E":
            continue
        _, at, carrier, proof, label, status = row
        if proofs.setdefault((carrier, proof), row) != row:
            raise ValueError(f"Conflicting receipt: {carrier}, {proof}")
        item = aliases.get((carrier, label), label)
        if item in roster and at <= cutoff and (item not in latest or at > latest[item][0]):
            latest[item] = (at, status)
    pending = {}
    for item in sorted(roster):
        at, status = latest.get(item, (None, "証跡なし"))
        if status != "受領":
            pending[item] = {"at": at, "status": status}
    completed = len(roster) - len(pending)
    if (completed, list(pending)) != oracle(packet):
        raise ValueError(f"Independent ledger disagreement: {packet['id']}")
    return {"cutoff": cutoff, "total": len(roster), "complete": completed,
            "pending": len(pending), "pending_items": pending}


def check_handoff(handoff, facts):
    match = HANDOFF.fullmatch(handoff)
    if not match:
        return None, ["unrecognized handoff wording"]
    details = re.findall(DETAIL, match["items"] or "")
    expected = facts["pending_items"]
    errors = [key for key in ("cutoff", "total", "complete", "pending")
              if match[key] != str(facts[key])]
    if sorted(item for item, _ in details) != sorted(expected):
        errors.append("pending_ids")
    if any(status and status != expected.get(item, {}).get("status")
           for item, status in details):
        errors.append("pending_item_status")
    return not errors, errors


def replay(root):
    sessions = read(root / "design/control-sessions.json")
    oracle = runpy.run_path(str(root / "method/volume/oracle.py"))["result_from_ledger"]
    cases = read(root / "inputs/dev-cases.json")
    ledgers = {case["id"]: ledger_facts(case, oracle) for case in cases
               if any(row.startswith("M|") for row in case["records"])}
    design = sorted((s["arm"], s["target"]) for s in sessions.values())
    if len(ledgers) != 2 or design != sorted((arm, target) for arm in ("v04", "proposal")
                                            for target in TARGET_INSTRUCTIONS):
        raise ValueError("Expected the frozen two ledgers and four control sessions")
    result_dir = root / "results/target-control"
    if {p.stem for p in result_dir.glob("*.json")} != set(sessions):
        raise ValueError("Missing or unexpected control session files")
    answers = []
    for session_id, session in sorted(sessions.items()):
        arm, target = session["arm"], session["target"]
        if session["added_instruction"] != TARGET_INSTRUCTIONS[target]:
            raise ValueError(f"Referent does not match the instruction: {session_id}")
        outputs = read(result_dir / f"{session_id}.json")
        if outputs.keys() != ledgers.keys():
            raise ValueError(f"Control case coverage differs: {session_id}")
        for case_id, output in sorted(outputs.items()):
            facts = ledgers[case_id]
            audit, errors = check_handoff(output["handoff"], facts)
            completion = facts["pending"] == 0 if target == "delivery" else audit
            expected = None if completion is None else ("complete" if completion else "open")
            correct = expected == output["state"] if expected is not None else None
            answers.append({"session": session_id, "arm": arm, "target": target, "case": case_id,
                            "state": output["state"], "expected_state": expected,
                            "state_correct": correct, "audit_complete": audit,
                            "handoff_errors": errors})
    return {"ledger_facts": ledgers, "answers": answers, "summary": {
        "answers": len(answers),
        "state_correct": sum(a["state_correct"] is True for a in answers),
        "audit_complete": sum(a["audit_complete"] is True for a in answers),
        "manual_review_needed": sum(a["audit_complete"] is None for a in answers),
    }}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="evaluation root containing design, inputs, method and results")
    report = replay(parser.parse_args().root)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    raise SystemExit(0 if all(a["state_correct"] and a["audit_complete"]
                              for a in report["answers"]) else 1)
