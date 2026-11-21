"""Score a delivery from the recorded shift, without importing candidate or generator code."""

import argparse
import json
from pathlib import Path


STATES = ("NO_CHECK", "CHECK_FAILED", "NO_RECEIPT", "CONFLICT", "READY")
ROW_KEYS = {"slot", "rev", "state", "check_seq", "receipt_seq"}
HANDOFF_KEYS = {"shift", "desk", "counts", "recovered"}


def expected(data):
    queue = []
    counts = dict.fromkeys(STATES, 0)
    recovered = []
    for plan in sorted(data["plan"], key=lambda entry: entry["slot"]):
        slot = plan["slot"]
        version = plan["rev"]
        checks = sorted((row for row in data["checks"] if (row["slot"], row["rev"]) == (slot, version)),
                        key=lambda row: row["seq"])
        receipt = max((row for row in data["receipts"]
                       if (row["slot"], row["rev"], row["desk"]) == (slot, version, data["desk"])),
                      key=lambda row: row["seq"], default=None)
        if not checks:
            state = "NO_CHECK"
        elif checks[-1]["result"] == "fail":
            state = "CHECK_FAILED"
        else:
            if any(row["result"] == "fail" for row in checks[:-1]):
                recovered.append(slot)
            if receipt is None:
                state = "NO_RECEIPT"
            elif receipt["code"] != plan["code"]:
                state = "CONFLICT"
            else:
                state = "READY"
        counts[state] += 1
        queue.append(dict(slot=slot, rev=version, state=state,
                          check_seq=checks[-1]["seq"] if checks else None,
                          receipt_seq=receipt["seq"] if receipt else None))

    handoff = dict(shift=data["shift"], desk=data["desk"], counts=counts, recovered=recovered)
    return queue, handoff


def reject_duplicates(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate key {key}")
        obj[key] = value
    return obj


def submitted(path):
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    except (ValueError, OSError, RecursionError):
        return None


def same(value, expected_value):
    # JSON distinguishes true, 1, and 1.0. Python equality does not.
    return type(value) is type(expected_value) and value == expected_value


def score(data, delivery):
    rows, expected_handoff = expected(data)
    queue = submitted(delivery / "queue.json")
    handoff = submitted(delivery / "handoff.json")
    names = {p.name for p in delivery.iterdir()} if delivery.is_dir() else set()
    list_of_rows = isinstance(queue, list) and all(isinstance(item, dict) for item in queue)
    handoff = handoff if isinstance(handoff, dict) else {}
    counts = handoff.get("counts")
    count_schema = isinstance(counts, dict) and set(counts) == set(STATES) and all(
        type(n) is int and n >= 0 for n in counts.values())
    recovered = handoff.get("recovered")

    def columns(*fields):
        return list_of_rows and len(rows) == len(queue) and all(
            key in actual and same(actual[key], wanted[key])
            for actual, wanted in zip(queue, rows) for key in fields)

    checks = dict(
        inventory=names == {"queue.json", "handoff.json"} and all(
            (delivery / name).is_file() and not (delivery / name).is_symlink() for name in names),
        queue_schema=list_of_rows and all(
            set(r) == ROW_KEYS and isinstance(r["slot"], str) and type(r["rev"]) is int
            and r["state"] in STATES and all(r[k] is None or type(r[k]) is int for k in ("check_seq", "receipt_seq"))
            for r in queue),
        queue_current=columns("slot", "rev"),
        queue_state=columns("slot", "state"),
        queue_evidence=columns("slot", "check_seq", "receipt_seq"),
        handoff_schema=set(handoff) == HANDOFF_KEYS and isinstance(handoff.get("shift"), str)
        and isinstance(handoff.get("desk"), str) and count_schema and isinstance(recovered, list)
        and all(isinstance(slot, str) for slot in recovered),
        handoff_route=all(handoff.get(k) == expected_handoff[k] for k in ("shift", "desk")),
        handoff_counts=count_schema and counts == expected_handoff["counts"],
        handoff_recovery=recovered == expected_handoff["recovered"],
    )
    holds = {state: [row["slot"] for row in rows if row["state"] == state]
             for state in STATES if state != "READY" and expected_handoff["counts"][state]}
    facts = dict(shift=data["shift"], desk=data["desk"], total=len(rows), ready=expected_handoff["counts"]["READY"],
                 holds=holds, recovered=expected_handoff["recovered"])
    return {"pass": all(checks.values()), "checks": checks, "report_facts": facts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="directory containing shift.json")
    parser.add_argument("--delivery", required=True, type=Path, help="directory containing candidate output")
    args = parser.parse_args()
    data = json.loads((args.input / "shift.json").read_text(encoding="utf-8"))
    print(json.dumps(score(data, args.delivery), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
