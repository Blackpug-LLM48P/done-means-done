"""Verify published fixtures from their public record contract without importing the generator."""

import json
import re
from collections import defaultdict
from pathlib import Path


DIR = Path(__file__).resolve().parent


def load(name):
    return json.loads((DIR / name).read_text(encoding="utf-8"))


def result_from_ledger(packet):
    deadline = re.search(r"同日 (\d\d:\d\d) 時点", packet["request"]).group(1)
    ledger = [row.split("|") for row in packet["records"]]
    targets = {item for kind, *rest in ledger if kind == "M" for item in rest[0].split(",")}
    alias_book = {(agency, short): canonical for kind, *rest in ledger if kind == "A"
                  for agency, short, canonical in [rest]}
    assert len(targets) == len(alias_book) and 45 <= len(targets) <= 65
    assert len({short for agency, short in alias_book}) < len(alias_book)
    receipts = {}
    for row in ledger:
        if row[0] == "E":
            _, at, agency, proof, label, status = row
            assert receipts.setdefault((agency, proof), row) == row
            assert status in {"保留", "取消", "受領"}
    assert len(receipts) < sum(row[0] == "E" for row in ledger)
    assert len({proof for agency, proof in receipts}) < len(receipts)

    # Group by canonical destination, then sort each destination's own eligible timeline.
    histories = defaultdict(list)
    for _, at, agency, proof, label, status in receipts.values():
        item = alias_book.get((agency, label), label)
        if item in targets and at <= deadline:
            histories[item].append((at, status))
    pending = []
    boundary_changed = False
    for item in sorted(targets):
        events = sorted(histories[item])
        assert len({at for at, _ in events}) == len(events)
        if len(events) > 1 and events[-1][0] == deadline:
            boundary_changed |= (events[-1][1] == "受領") != (events[-2][1] == "受領")
        if not events or events[-1][1] != "受領":
            pending.append(item)
    assert boundary_changed
    return len(targets) - len(pending), pending


def verify(split, expected_size):
    packets = load(f"{split}-cases.json")
    key = load(f"{split}-key.json")
    pairs = load(f"{split}-pairs.json")
    ids = [packet["id"] for packet in packets]
    assert len(ids) == len(set(ids)) == expected_size
    assert set(ids) == set(key)
    assert all(len(pair) == 2 for pair in pairs)
    assert sorted(i for pair in pairs for i in pair) == sorted(ids)
    assert all({key[i]["state"] for i in pair} == {"open", "complete"} for pair in pairs)
    assert (DIR / f"{split}-cases.json").stat().st_size < 80000

    for packet in packets:
        assert set(packet) == {"id", "request", "records", "draft"}
        assert all(isinstance(record, str) for record in packet["records"])
        count, pending = result_from_ledger(packet)
        answer = key[packet["id"]]
        assert set(answer) == {"state", "required", "forbidden", "rationale"}
        assert answer["state"] == ("open" if pending else "complete")
        assert answer["required"] == [
            f"完了は{count}件", f"未完了は{len(pending)}件",
            *(f"未完了の正式荷番は{item}" for item in pending),
        ]
        assert answer["forbidden"] and answer["rationale"]
    return set(ids)


if __name__ == "__main__":
    dev = verify("dev", 2)
    hold = verify("hold", 4)
    assert dev.isdisjoint(hold)
    print("Verified both fixture shapes, balance, pairing, and independent ledger verdicts.")
