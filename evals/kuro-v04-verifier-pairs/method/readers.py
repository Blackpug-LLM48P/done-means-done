"""Blind readers to the conditions, model responses and fixed decisions.

--prepare DEST writes packet.json. Two independent readers write first.json and
second.json. --disputes DEST seals both and exports only the contested cases.
A third reader supplies third.json if needed. --finalize DEST resolves the votes
and compares the readers separately with the verifier and the fixed expectation.
--check replays the complete published record.
"""
import argparse
import importlib.util
from pathlib import Path
import re
import secrets
import subprocess
import sys

STUDY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STUDY.parents[1]))
from integrations.evidence_handoff import body_review, route

# Reuse the immutable publication and strict JSON ballot parser from the baseline.
spec = importlib.util.spec_from_file_location("candidate_blind", STUDY.parent / "kuro-v04-candidate/method/blind.py")
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)
seal, encode, require = baseline.seal, baseline.encode, baseline.require
read_ballot = baseline.ballots.read_ballot


def packets(study):
    units = route.read_json(study / "inputs/units.json")
    require(isinstance(units, list) and len(units) <= 16, "unexpected unit count")
    rows = {}
    for unit in units:
        uid, case, body = unit["id"], unit["case"], unit["body"]
        require(route.nonblank(uid) and uid not in rows, "invalid or duplicate unit ID")
        trace = body_review.apply_review(case, body, unit["r1_raw"])
        require(trace["status"] == "flagged" and trace["proposed_body"] != body, f"{uid}: invalid candidate")
        visible = body_review.make_packet(case, body)["records"]
        rows[uid] = {"records": [r["text"] for r in visible], "original": body, "candidate": trace["proposed_body"]}
    receipts = study / "results/live/receipts"
    require(rows.keys() == {p.stem for p in receipts.glob("*.json")}, "capture incomplete")
    return rows


def indexed(study, create):
    rows = packets(study)
    path = study / "results/reader-aliases.json"
    if create and not path.exists():
        if rows:
            subprocess.run([sys.executable, "-B", study / "method/live.py", "--check"], check=True)
        aliases = {"T-" + secrets.token_hex(16): {"unit_id": uid, "packet_sha256": body_review.digest(row)}
                   for uid, row in rows.items()}
        require(len(aliases) == len(rows), "alias collision")
        seal(path, encode(aliases))
    aliases = route.read_json(path)
    require(isinstance(aliases, dict) and len(aliases) == len(rows), "alias count")
    packet = {}
    for label, link in sorted(aliases.items()):
        require(re.fullmatch(r"T-[0-9a-f]{32}", label) and isinstance(link, dict)
                and set(link) == {"unit_id", "packet_sha256"} and link["unit_id"] in rows, "invalid alias binding")
        row = rows.pop(link["unit_id"])
        require(link["packet_sha256"] == body_review.digest(row), "reader packet changed")
        packet[label] = row
    require(not rows, "unit absent from aliases")
    return aliases, packet


def vote(path, labels):
    # A zero-case study or empty arbitration has no reader work.
    if not labels and not path.exists():
        return encode({}), {}
    blob, data = read_ballot(path)
    require(isinstance(data, dict) and data.keys() == labels.keys(), f"{path.name}: case coverage differs")
    for label, record in data.items():
        require(isinstance(record, dict) and set(record) == {"action", "reason"}
                and record["action"] in ("offer", "hold") and route.nonblank(record["reason"]),
                f"{path.name}/{label}: action and reason required")
    return blob, data


def summary(aliases, votes, disputes, third, events):
    by_id = {e["unit_id"]: e for e in events}
    require(len(by_id) == len(events) == len(aliases)
            and set(by_id) == {v["unit_id"] for v in aliases.values()}, "primary event coverage differs")
    units = {}
    for label, link in aliases.items():
        uid = link["unit_id"]
        row = by_id[uid]
        action = third[label]["action"] if label in disputes else votes[0][label]["action"]
        require(row["valid"] == (row["observed"] in ("offer", "hold")), f"{uid}: unclassified verifier action")
        units[uid] = {"reader": action, "readers_agreed": label not in disputes, "alias": label,
                      "expected": row["expected"], "verifier": row["observed"], "transport": row["transport"],
                      "validation_error": row["validation_error"], "verifier_matched_reader": (
                          row["observed"] == action if row["valid"] else None),
                      "key_matched_reader": row["expected"] == action}
    disputed = sorted(uid for uid, u in units.items() if not u["readers_agreed"])
    comparable = [u for u in units.values() if u["verifier_matched_reader"] is not None]
    unclassified = sorted(uid for uid, u in units.items() if u["verifier_matched_reader"] is None)
    verifier_agree = sum(u["verifier_matched_reader"] for u in comparable)
    key_agree = sum(u["key_matched_reader"] for u in units.values())
    return {"units": units, "disputed_ids": disputed,
            "reader_agreement": {"cases": len(units), "agreed": len(units) - len(disputed),
                                 "arbitrated": len(disputed)},
            "verifier_vs_reader": {"cases": len(units), "valid_decisions": len(comparable), "agreed": verifier_agree,
                                   "disagreed": len(comparable) - verifier_agree, "unclassified_ids": unclassified,
                                   "invalid_response_ids": [i for i in unclassified if units[i]["transport"] == "ok"],
                                   "transport_error_ids": [i for i in unclassified if units[i]["transport"] != "ok"]},
            "key_vs_reader": {"cases": len(units), "agreed": key_agree, "disagreed": len(units) - key_agree}}


def run(study, action, dest=None):
    result = study / "results"
    folder = result / "reader-ballots"
    aliases, packet = indexed(study, action == "prepare")
    if action == "prepare":
        seal(dest / "packet.json", encode(packet))
        print(f"{len(packet)} blinded proposals")
        return
    if action != "check":
        require((dest / "packet.json").read_bytes() == encode(packet), "reader packet differs")
    origin = folder if action == "check" else dest
    votes = []
    for name in ("first.json", "second.json"):
        blob, reader = vote(origin / name, packet)
        if action == "disputes":
            seal(folder / name, blob)
        else:
            require((folder / name).read_bytes() == blob, f"{name}: first-round ballot changed")
        votes.append(reader)
    disputed = {k: row for k, row in packet.items() if votes[0][k]["action"] != votes[1][k]["action"]}
    if action == "disputes":
        seal(dest / "disputes.json", encode(disputed))
        print(f"{len(disputed)} contested proposals")
        return
    if action == "finalize":
        require((dest / "disputes.json").read_bytes() == encode(disputed), "dispute packet differs")
    third_blob, third = vote(origin / "third.json", disputed)
    subprocess.run([sys.executable, "-B", study / "method/score.py", "--check"], check=True)
    data = summary(aliases, votes, disputed, third, route.read_json(result / "events.json"))
    outputs = {folder / "third.json": third_blob, result / "reader-summary.json": encode(data)}
    for path, content in outputs.items():
        if action == "finalize":
            seal(path, content)
        else:
            require(path.read_bytes() == content, f"{path.name}: differs from replay")
    require({p.name for p in folder.glob("*.json")} == {"first.json", "second.json", "third.json"},
            "published reader ballot coverage differs")
    print(f"{len(packet)} proposals graded, {len(disputed)} arbitrated")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group(required=True)
    for name in ("prepare", "disputes", "finalize"):
        options.add_argument("--" + name, type=Path, metavar="DEST")
    options.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for operation, folder in vars(args).items():
        if folder:
            run(STUDY, operation, None if operation == "check" else folder)
