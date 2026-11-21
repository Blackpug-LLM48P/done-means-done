"""Blind the original and R1 candidate together, then replay two votes and disputed-only arbitration.

--prepare DEST writes packet.json. Independent readers return first.json and second.json.
--disputes DEST seals their ballots and writes disputes.json, with contested texts only.
A third reader returns third.json for these texts. --finalize DEST publishes item-level
arbitration and per-unit grades. --check replays the published record without DEST.
"""
import argparse
import importlib.util
import os
from pathlib import Path
import secrets
import sys
import tempfile

STUDY = Path(__file__).resolve().parents[1]
REPO = STUDY.parents[1]
sys.path.insert(0, str(REPO))
from integrations.evidence_handoff import body_review, route

spec = importlib.util.spec_from_file_location("ambiguity_blind", STUDY.parent / "kuro-v04-ambiguity/method/blind.py")
ballots = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ballots)
encode, require = ballots.encode, ballots.require


def seal(path, data):
    """Publish once, or confirm that a concurrent/previous publication is identical."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        pending = Path(tmp.name)
        try:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
            try:
                os.link(pending, path)
            except FileExistsError:
                require(path.read_bytes() == data, f"{path.name}: refusing to replace existing record")
        finally:
            pending.unlink(missing_ok=True)


def keyed(rows):
    expected = {f"N{i:02d}" for i in range(1, 13)}
    require(isinstance(rows, list) and len(rows) == len(expected), "expected twelve fresh units")
    result = {r["id"]: r for r in rows}
    require(result.keys() == expected, "unit coverage")
    return result


def review_groups(study):
    units = keyed(route.read_json(study / "inputs/units.json"))
    gold = keyed(route.read_json(study / "inputs/gold.json"))
    folder = study / "results/live/review/receipts"
    require({p.stem for p in folder.glob("*.json")} == units.keys(), "R1 receipt coverage")
    groups = {}
    for uid, unit in units.items():
        case, body = unit["case"], unit["body"]
        facts = gold[uid]["required"]
        require(isinstance(facts, list) and len(facts) == 2 and all(route.nonblank(f) for f in facts),
                f"{uid}: invalid mandatory facts")
        receipt = route.read_json(folder / f"{uid}.json")
        require(receipt["unit_id"] == uid and receipt["stage"] == "review", f"{uid}: wrong review receipt")
        trace = body_review.apply_review(case, body, receipt["raw"])
        require(encode(receipt["trace"]) == encode(trace) and trace["packet_sha256"] == receipt["packet_sha256"],
                f"{uid}: stored candidate differs from raw evidence")
        candidate = body if trace["status"] == "invalid" or receipt["meta"]["status"] != "ok" else trace["proposed_body"]
        for variant, text in (("original", body), ("candidate", candidate)):
            packet = body_review.make_packet(case, text)
            key = (packet["source_sha256"], text)
            row = {"facts": facts, "packet": packet}
            group = groups.setdefault(key, {"row": row, "variants": []})
            require(group["row"] == row, f"{uid}: incompatible duplicate")
            group["variants"].append([uid, variant])
    return groups


def index(study, create=False):
    groups = review_groups(study)
    path = study / "results/aliases.json"
    if create and not path.exists():
        fresh = {"T-" + secrets.token_hex(16): ballots.binding(k, g) for k, g in groups.items()}
        require(len(groups) == len(fresh), "alias collision")
        seal(path, encode(fresh))
    aliases = route.read_json(path)
    available = {encode(ballots.binding(k, g)): g["row"] for k, g in groups.items()}
    require(isinstance(aliases, dict) and len(aliases) == len(groups), "alias coverage")
    rows = {}
    for label, link in aliases.items():
        require(ballots.ALIAS.fullmatch(label) and encode(link) in available, "invalid or duplicate alias binding")
        rows[label] = available.pop(encode(link))
    require(not available, "unassigned texts")
    return aliases, rows


def read_votes(folder, rows):
    votes, blobs = [], {}
    for name in ("first.json", "second.json"):
        blob, vote = ballots.read_ballot(folder / name)
        require(isinstance(vote, dict) and vote.keys() == rows.keys(), f"{name}: alias coverage")
        for label in rows:
            ballots.validate(rows[label], vote[label], f"{name}/{label}")
        votes.append(vote)
        blobs[name] = blob
    return votes, blobs


def run(study, action, dest=None):
    aliases, rows = index(study, create=action == "prepare")
    result = study / "results"
    published = result / "ballots"
    if action == "prepare":
        seal(dest / "packet.json", encode(rows))
        print(f"{len(rows)} blinded texts prepared")
        return
    if action != "check":
        require((dest / "packet.json").read_bytes() == encode(rows), "packet changed")
    votes, blobs = read_votes(published if action == "check" else dest, rows)
    disputes = ballots.disagreements(*votes)
    packet = {label: rows[label] for label in disputes}
    if action == "disputes":
        for name, blob in blobs.items():
            seal(published / name, blob)
        seal(dest / "disputes.json", encode(packet))
        print(f"{len(disputes)} contested texts")
        return
    folder = published if action == "check" else dest
    if action == "finalize":
        require((dest / "disputes.json").read_bytes() == encode(packet), "dispute packet changed")
        for name, blob in blobs.items():
            require((published / name).read_bytes() == blob, f"{name}: reader ballot changed after sealing")
    third_file = folder / "third.json"
    third_blob, third = (ballots.read_ballot(third_file) if disputes or third_file.exists()
                         else (encode({}), {}))
    decisions = ballots.resolve(rows, *votes, third)
    outputs = {published / "third.json": third_blob,
               result / "arbitration.json": encode({"disputes": disputes, "third": third}),
               result / "grades.json": encode(ballots.expanded(aliases, decisions))}
    for path, content in outputs.items():
        if action == "finalize":
            seal(path, content)
        else:
            require(path.read_bytes() == content, f"{path.name}: published result differs from replay")
    require({p.name for p in published.glob("*.json")} == {*blobs, "third.json"}, "published ballot coverage")
    print(f"12 units × 2 variants, {len(rows)} distinct texts, {len(disputes)} contested texts")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    for operation in ("prepare", "disputes", "finalize"):
        group.add_argument("--" + operation, type=Path, metavar="DEST")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for operation, dest in vars(args).items():
        if dest:
            run(STUDY, operation, dest if operation != "check" else None)
            return


if __name__ == "__main__":
    main()
