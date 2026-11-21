"""Generate only the fictional input records for one shift."""

import argparse
import json
import random
import re
from pathlib import Path


def build(seed, kind):
    rng = random.Random(int(seed, 16))
    desks = ["若葉調整室", "浜風調整室", "こまち調整室", "夕凪調整室", "月見調整室"]
    desk, alternate = rng.sample(desks, 2)
    shift = f"FM-{rng.randint(10000, 99999)}"
    if kind == "mixed":
        patterns = ["ready", "ready", "absent", "conflict", "fail", "unchecked"]
        patterns += rng.choices(["ready", "absent", "conflict"], k=rng.randint(0, 2))
    elif kind == "clean":
        patterns = ["ready"] * rng.randint(4, 7)
    else:
        patterns = ["absent", "conflict", "fail", "unchecked"]
        patterns += rng.choices(patterns, k=rng.randint(0, 2))
    rng.shuffle(patterns)
    slots = rng.sample(range(100, 1000), len(patterns))
    passing = [i for i, pattern in enumerate(patterns) if pattern in {"ready", "absent", "conflict"}]
    recovered = set(rng.sample(passing, rng.randint(1, min(2, len(passing)))))
    series = {"checks": [], "receipts": []}
    clock = rng.randint(10, 100)

    def record(group, slot, rev, **details):
        nonlocal clock
        clock += rng.randint(1, 9)
        series[group].append(dict(seq=clock, slot=slot, rev=rev, **details))

    plan = []
    for i, (number, pattern) in enumerate(zip(slots, patterns)):
        slot = f"P-{number}"
        rev = rng.randint(2, 12)
        code = f"M-{rng.randrange(16**5):05X}"
        other = f"M-{(int(code[2:], 16) ^ 1):05X}"
        plan.append(dict(slot=slot, rev=rev, code=code))

        # A failure on a past version can look like a current recovery.
        record("checks", slot, rev - 1, result="fail")
        if i in recovered:
            record("checks", slot, rev, result="fail")
        if pattern == "fail":
            record("checks", slot, rev, result="pass")
        if pattern != "unchecked":
            record("checks", slot, rev, result="fail" if pattern == "fail" else "pass")

        if pattern != "absent":
            # A previous receipt for the right desk may have the opposite verdict.
            if rng.getrandbits(1) or i == 0:
                record("receipts", slot, rev, desk=desk, code=code if pattern == "conflict" else other)
            record("receipts", slot, rev, desk=desk, code=other if pattern == "conflict" else code)

        # The newest events can refer to the wrong revision or the wrong desk.
        record("checks", slot, rev - 1, result=rng.choice(["pass", "fail"]))
        record("receipts", slot, rev - 1, desk=desk, code=code)
        record("receipts", slot, rev, desk=alternate, code=code)

    for records in [plan, *series.values()]:
        rng.shuffle(records)
    return dict(shift=shift, desk=desk, plan=plan, **series)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--kind", required=True, choices=("mixed", "clean", "blocked"))
    parser.add_argument("--out", required=True, type=Path, help="directory for shift.json")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", args.seed):
        parser.error("--seed requires 64 hexadecimal digits")
    data = build(args.seed, args.kind)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "shift.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
