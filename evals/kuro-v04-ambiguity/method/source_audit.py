"""Compare the two sealed source-only audits against the authors' pre-sampling labels."""
import argparse
from pathlib import Path

from materialize import LANES, STUDY, read, sha, unit_id, wire


def summarize():
    files = STUDY / "results/source-ballots"
    committed = read(STUDY / "design/source-audit-sha256.json")
    votes = []
    for name in ("source-1.json", "source-2.json"):
        path = files / name
        assert sha(path.read_bytes()) == committed[name], "pre-sampling source vote changed"
        votes.append(read(path))
    gold = read(STUDY / "inputs/gold.json")
    details = {}
    for tag in LANES:
        for family in read(STUDY / "inputs/families" / (tag + ".json")):
            fid = family["family_id"]
            for sid in family["sources"]:
                bids = set(family["bodies"])
                targets = {bid: gold[unit_id(fid, sid, bid)] for bid in bids}
                expected = sorted(bid for bid, g in targets.items() if not g["bad_sentence_ids"])
                actual = []
                for reader in votes:
                    v = reader[sid]
                    supported = v["supported"]
                    assert isinstance(v["reason"], str) and v["reason"].strip()
                    assert len(supported) == len(set(supported)) and set(supported) <= bids
                    actual.append(sorted(supported))
                details[sid] = dict(family=fid, source_role=next(iter(targets.values()))["source_role"],
                                    author=expected, readers=actual, agree_with_author=[a == expected for a in actual])
    assert len(details) == 12 and all(reader.keys() == details.keys() for reader in votes)
    return {"source_count": len(details), "reader_agreements": sum(r["readers"][0] == r["readers"][1] for r in details.values()),
            "both_match_author": sum(all(r["agree_with_author"]) for r in details.values()), "sources": details}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--write", action="store_true")
    args = p.parse_args()
    path = STUDY / "results/source-audit.json"
    data = wire(summarize())
    if args.write:
        path.write_bytes(data)
    else:
        assert path.read_bytes() == data
        print("Both pre-sampling audits of twelve source variants replayed.")
