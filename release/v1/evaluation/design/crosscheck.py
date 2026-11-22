"""Independently rebuild all answer cells on the operator host. Print counts only."""
import argparse
import csv
import hashlib
import json
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from grader import compare


def read_input_rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def independently_derive(packet):
    inventory = sorted(read_input_rows(packet / "items.csv"), key=lambda item: item["item"])
    components = defaultdict(Counter)
    for part in read_input_rows(packet / "parts.csv"):
        components[part["item"]][part["component"]] += int(part["units"])

    cutoff = json.loads((packet / "scope.json").read_bytes())["cutoff"]
    events = sorted(read_input_rows(packet / "events.csv"), key=lambda event: int(event["serial"]))
    latest = {}
    for event in events:
        if int(event["serial"]) > cutoff:
            break
        latest[(event["item"], event["revision"], event["topic"])] = event["value"]

    register = [["item", "title", "units", "release", "inspection"]]
    files = {"register.csv": register}
    ready, held, uninspected = [], [], []
    for record in inventory:
        item, revision = record["item"], record["revision"]
        state = latest.get((item, revision, "release"), "hold")
        inspection = latest.get((item, revision, "inspection"), "unknown")
        detail = components[item]
        register.append([item, record["title"], str(sum(detail.values())), state, inspection])
        if state == "ready":
            ready.append(item)
            files[f"items/{item}.csv"] = [["item", "component", "units"]] + [
                [item, name, str(quantity)] for name, quantity in sorted(detail.items())
            ]
        else:
            held.append(item)
        if inspection != "checked":
            uninspected.append(item)
    return files, {"ready": ready, "hold": held, "checked_count": len(inventory) - len(uninspected),
                   "item_count": len(inventory), "inspection_open": uninspected}


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerows(rows)


def check_synthetic_controls(key, files):
    # Every delivery read by compare() below is created here and discarded here.
    controls = 0
    correct = True
    with tempfile.TemporaryDirectory() as workspace:
        delivery = Path(workspace)
        for name, rows in files.items():
            target = delivery / name
            target.parent.mkdir(exist_ok=True, parents=True)
            write_csv(target, rows)
        original = compare(key, delivery)
        correct &= original == {"all_correct": True, "matched": sorted(files), "wrong": [],
                                "missing": [], "unexpected": []}
        for name, rows in files.items():
            # Column 3 is a unit count in both CSV formats. Change exactly one data cell.
            altered = [row.copy() for row in rows]
            altered[1][2] = str(int(altered[1][2]) + 1)
            write_csv(delivery / name, altered)
            observed = compare(key, delivery)
            correct &= observed == {"all_correct": False, "matched": sorted(set(files) - {name}),
                                    "wrong": [name], "missing": [], "unexpected": []}
            controls += 1
            write_csv(delivery / name, rows)
    return correct, controls


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check_pack(root):
    manifest = json.loads((root / "commitments.json").read_bytes())
    mapping_bytes = (root / "operator" / "allocation.json").read_bytes()
    mapping = json.loads(mapping_bytes)
    seals = {record["packet"]: record for record in manifest["packets"]}
    if (sha(mapping_bytes) != manifest["allocation_sha256"] or len(manifest["packets"]) != 8
            or set(mapping) != {f"C{index:02d}" for index in range(1, 9)}
            or len(seals) != 8 or set(seals) != set(mapping.values())):
        raise ValueError("invalid manifest")
    counts = Counter()
    for case, packet_id in sorted(mapping.items()):
        packet = root / "packets" / packet_id
        paths = sorted(packet.iterdir())
        if {p.name for p in paths} != {"request.txt", "scope.json", "parts.csv", "items.csv", "events.csv"}:
            raise ValueError("invalid packet")
        file_hashes = {p.name: sha(p.read_bytes()) for p in paths}
        digest_input = (json.dumps(file_hashes, sort_keys=True, indent=2) + "\n").encode()
        sealed = (root / "operator" / f"{packet_id}.json").read_bytes()
        key = json.loads(sealed)
        if (sha(sealed) != seals[packet_id]["key_sha256"] or sha(digest_input) != seals[packet_id]["input_sha256"]
                or key["case"] != case):
            raise ValueError("commitment mismatch")
        expected, facts = independently_derive(packet)
        counts["packets"] += 1
        counts["files"] += len(expected)
        counts["cells_including_headers"] += sum(len(row) for rows in expected.values() for row in rows)
        counts["facts_fields"] += len(facts)
        cells_and_facts_match = expected == key["expected"] and facts == key["source_facts"]
        controls_pass, mutations = check_synthetic_controls(key, expected)
        counts["positive_controls"] += 1
        counts["single_cell_negative_controls"] += mutations
        counts["failed_packets"] += int(not (cells_and_facts_match and controls_pass))
    return dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operator_pack", type=Path, help="Root created by prepare.py, never a worker delivery")
    args = parser.parse_args()
    try:
        totals = check_pack(args.operator_pack)
    except (OSError, ValueError, KeyError, TypeError, IndexError, csv.Error):
        print(json.dumps({"pass": False, "reason": "invalid_or_incomplete_operator_pack"}))
        return 1
    ok = totals["failed_packets"] == 0
    print(json.dumps({"pass": ok, **totals}, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
