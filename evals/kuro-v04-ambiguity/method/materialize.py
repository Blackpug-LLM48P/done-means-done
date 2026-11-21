"""Expand paired stimuli and, after capture, independently committed author ballots."""
import argparse
import hashlib
import json
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
PR11 = STUDY.parent / "kuro-v04-body"
PR9 = STUDY.parent / "kuro-v04-receiver"
LANES = ("amber", "blue")


def read(path):
    return json.loads(path.read_text())


def wire(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unit_id(fid, source, body):
    return "P-" + sha(wire([fid, source, body]))[:16]


def histories():
    t = next(c for c in read(PR9 / "inputs/cases.json") if c["case_id"] == "T2K7F")
    j = next(c for c in read(PR11 / "inputs/cases.json") if c["case_id"] == "J7814")
    old = read(PR11 / "inputs/gold.json")
    for uid, r in read(PR11 / "inputs/historical.json").items():
        yield uid, t, r["body"], "historical", r["bad_sentence_ids"], r["unsupported_core"] or None, r["facts"]
    diag = read(PR11 / "results/units/A2948.json")
    yield "A2948", j, diag["body"], "diagnostic", [], None, old["cases"]["J7814"]["facts"]


def expand(lanes):
    units = []
    for group in lanes.values():
        assert len(group) == 2
        for f in group:
            sources = f["sources"]
            bodies = f["bodies"]
            assert len(sources) == len(bodies) == len(set(bodies.values())) == 3
            base = next(iter(sources.values()))
            for c in sources.values():
                assert {k:v for k,v in c.items() if k!="records"} == {k:v for k,v in base.items() if k!="records"}
                assert len(base["records"]) == len(c["records"])
                assert all({k:v for k,v in x.items() if k!="text"} == {k:v for k,v in y.items() if k!="text"}
                           for x,y in zip(base["records"],c["records"]))
            changed = [i for i in range(len(base["records"])) if len({v["records"][i]["text"] for v in sources.values()}) != 1]
            assert len(changed) == 1 and len({c["records"][changed[0]]["text"] for c in sources.values()}) == 3
            for sid,c in sources.items():
                for bid,b in bodies.items():
                    units.append(dict(id=unit_id(f["family_id"],sid,bid),family_id=f["family_id"],
                                      case=c,body=b,group="challenge"))
    for uid,c,b,g,*_ in histories():
        units.append(dict(id=uid,case=c,body=b,family_id=c["case_id"],group=g))
    assert len(units) == len({u["id"] for u in units}) == 41
    assert len({u["family_id"] for u in units if u["group"]=="challenge"}) == 4
    return sorted(units,key=lambda u:u["id"])


def open_key(lanes, private):
    gold = {}
    for tag, families in lanes.items():
        answers = read(private / (tag + ".json"))
        assert set(answers) == {f["family_id"] for f in families}
        for f in families:
            g = answers[f["family_id"]]
            assert set(g["source_roles"]) == set(f["sources"]) and set(g["body_roles"]) == set(f["bodies"])
            assert set(g["source_roles"].values()) == {"a","b","ambiguous"}
            assert set(g["body_roles"].values()) == {"a","b","neutral"}
            assert len(g["facts"]) == 2 and all(g["facts"])
            for sid, sr in g["source_roles"].items():
                for bid, br in g["body_roles"].items():
                    uid = unit_id(f["family_id"],sid,bid)
                    bad = br != "neutral" and br != sr
                    target = g["targets"][bid] if bad else None
                    if bad:
                        assert target["core"] in f["bodies"][bid] and target["sentence_id"] >= 1
                    gold[uid] = dict(source_role=sr,body_role=br,bad_sentence_ids=[target["sentence_id"]] if bad else [],
                                     core=target["core"] if bad else None,facts=g["facts"],ref=g["ref"])
    for uid,c,b,g,ids,core,facts in histories():
        gold[uid] = dict(source_role=g,body_role=g,bad_sentence_ids=ids,core=core,facts=facts,ref=None)
    return gold


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("inputs","open","check"))
    p.add_argument("--answers", type=Path)
    args=p.parse_args()
    lanes={t:read(STUDY/"inputs/families"/(t+".json")) for t in LANES}
    units=expand(lanes)
    dest=STUDY/"inputs/units.json"
    if args.mode=="inputs":
        with dest.open("xb") as file: file.write(wire(units))
        return
    assert dest.read_bytes()==wire(units)
    commitments=read(STUDY/"design/commitments.json")
    answers=args.answers or STUDY/"inputs/author-keys"
    for tag in LANES:
        assert sha((answers/(tag+".json")).read_bytes()) == commitments[tag]
    key=wire(open_key(lanes,answers))
    if args.mode=="open":
        assert len(list((STUDY/"results/receipts").glob("*.json"))) == 82
        assert (STUDY/"results/runs.json").exists()
        with (STUDY/"inputs/gold.json").open("xb") as file: file.write(key)
    else:
        assert (STUDY/"inputs/gold.json").read_bytes() == key
        print("Verified 41 inputs and fixed labels from two independently committed keys.")


if __name__=="__main__":
    main()
