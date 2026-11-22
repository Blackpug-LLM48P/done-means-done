"""Check the oracle against a hand-calculated miniature and exercise the dummy strata."""
import json
import tempfile
from pathlib import Path

from grader import compare, reference
from prepare import digest, packet_digest, prepare


def check_manual(root):
    packet = root / "manual"
    packet.mkdir()
    (packet / "items.csv").write_text("item,title,revision\nB,板,r2\nA,塔,r3\n")
    (packet / "parts.csv").write_text("item,component,units\nA,Z,2\nB,Q,7\nA,Y,4\nA,Z,3\n")
    (packet / "events.csv").write_text(
        "serial,item,revision,topic,value\n"
        "4,A,r3,release,ready\n1,B,r1,release,ready\n5,B,r2,inspection,checked\n"
        "2,A,r3,release,hold\n6,A,r3,release,hold\n3,A,r2,inspection,checked\n"
    )
    (packet / "scope.json").write_text('{"cutoff":5}')
    key = reference(packet)
    delivery = root / "delivery"
    (delivery / "items").mkdir(parents=True)
    reg = delivery / "register.csv"
    detail = delivery / "items/A.csv"
    reg.write_text("item,title,units,release,inspection\nA,塔,9,ready,unknown\nB,板,7,hold,checked\n")
    detail.write_text("item,component,units\nA,Y,4\nA,Z,5\n")
    assert compare(key, delivery)["all_correct"]
    assert key["source_facts"] == {"ready": ["A"], "hold": ["B"], "checked_count": 1,
                                   "item_count": 2, "inspection_open": ["A"]}
    detail.write_text("item,component,units\nA,Y,4\nA,Z,4\n")
    assert compare(key, delivery)["wrong"] == ["items/A.csv"]
    detail.unlink()
    (delivery / "items/B.csv").write_text("item,component,units\nB,Q,7\n")
    result = compare(key, delivery)
    assert result["missing"] == ["items/A.csv"] and result["unexpected"] == ["items/B.csv"]
    print("hand-calculated cells and source facts: PASS")
    print("wrong total, missing required file, extra held file: PASS")


def check_collection(root):
    target = root / "dummy"
    prepare(target, dummy=True)
    seals = json.loads((target / "commitments.json").read_bytes())
    assert seals["dummy"] and len(seals["packets"]) == 8
    allocation_data = (target / "operator/allocation.json").read_bytes()
    assert digest(allocation_data) == seals["allocation_sha256"]
    allocation = json.loads(allocation_data)
    observed = set()
    for receipt in seals["packets"]:
        packet = target / "packets" / receipt["packet"]
        data = (target / "operator" / (receipt["packet"] + ".json")).read_bytes()
        assert allocation[json.loads(data)["case"]] == receipt["packet"]
        assert digest(data) == receipt["key_sha256"] and packet_digest(packet) == receipt["input_sha256"]
        assert {p.name for p in packet.iterdir()} == {"scope.json", "events.csv", "items.csv", "parts.csv", "request.txt"}
        key = json.loads(data)
        facts = key["source_facts"]
        case = int(key["case"][1:])
        observed.add(case)
        assert bool(facts["hold"]) == (case in (3, 4))
        assert bool(facts["inspection_open"]) == (case in (5, 6))
        if case in (7, 8):
            import csv
            with (packet / "items.csv").open() as stream:
                versions = {r["item"]: r["revision"] for r in csv.DictReader(stream)}
            cutoff = json.loads((packet / "scope.json").read_text())["cutoff"]
            with (packet / "events.csv").open() as stream:
                histories = [r for r in csv.DictReader(stream) if int(r["serial"]) <= cutoff
                             and r["revision"] == versions[r["item"]]]
            rejected = [r for r in histories if r["topic"] == "attempt" and r["value"] == "rejected"]
            assert len(rejected) == 2
            for earlier in rejected:
                assert any(r["item"] == earlier["item"] and r["value"] == "accepted"
                           and int(r["serial"]) > int(earlier["serial"]) for r in histories)
    assert observed == set(range(1, 9))
    print("dummy only: 8 packets / 4 strata / 16 commitments / exact worker filenames: PASS")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as temp:
        check_manual(Path(temp))
        check_collection(Path(temp))
