"""Build shuffled source ballots and matched candidate packets; reproduce eligibility and labels."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

STUDY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STUDY.parents[1]))
from integrations.evidence_handoff import body_review, candidate_check, route


def wire(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def require(test, reason):
    if not test:
        raise ValueError(reason)


def token(*parts):
    return hashlib.sha256(("PR14-v1\0" + "\0".join(parts)).encode()).hexdigest()[:16]


def publish(path, value, check=False):
    data = wire(value)
    if check or path.exists():
        require(path.read_bytes() == data, f"{path.name} differs from replay")
    else:
        path.parent.mkdir(exist_ok=True, parents=True)
        with path.open("xb") as f:
            f.write(data)


def families():
    records = [row for name in "abc" for row in route.read_json(STUDY / f"inputs/authors/author-{name}.json")]
    require([r["family"] for r in records] == [f"F{i}" for i in range(1,7)], "family coverage")
    for r in records:
        require(len(r["facts"]) == 2 and all(route.nonblank(x) for x in r["facts"]), "two separate facts")
        require(all(route.nonblank(r[k]) for k in ("original","candidate_b","candidate_common","record_a",
                                                  "record_b","record_ambiguous","reading_a","reading_b")),
                "missing text")
        require(len(body_review.sentences(r["original"])) == 1, "R1 edit must locate one complete sentence")
    return records


def source_rows(records):
    packet, expected = {}, {}
    for r in records:
        for src in ("ambiguous","a","b"):
            fid = r["family"]
            alias = token("source", fid, src)
            order = sorted("ab", key=lambda k:token("order", alias, k))
            options = {str(i):r["reading_"+k] for i,k in enumerate(order,1)}
            packet[alias] = dict(records=[r["record_"+src], *r["facts"]], readings=options)
            expected[alias] = dict(family=fid, source=src,
                                   allowed=sorted(str(i) for i,k in enumerate(order,1) if src in (k,"ambiguous")))
    return packet, expected


def qualify(expected, reads):
    require(all(b.keys() == expected.keys() for b in reads), "incomplete independent source audit")
    rows, eligible = {}, []
    for label, target in expected.items():
        both = []
        for ballot in reads:
            vote = ballot[label]
            choices = vote["allowed"]
            require(isinstance(choices,list) and set(choices) <= {"1","2"} and len(choices)==len(set(choices))
                    and route.nonblank(vote["reason"]), "invalid source ballot")
            both.append(sorted(choices))
        rows[label] = dict(**target, votes=both, qualified=all(v==target["allowed"] for v in both))
    for fid in sorted({r["family"] for r in rows.values()}):
        if all(row["qualified"] for row in rows.values() if row["family"] == fid):
            eligible.append(fid)
    return dict(rows=rows, eligible=eligible, selected=eligible[:4])


CELLS = [("ambiguous","common","offer"), ("ambiguous","b","hold"), ("a","b","hold"), ("b","b","offer")]


def units_for(records, selected):
    units, keys = [], []
    for r in records:
        family = r["family"]
        if family not in selected:
            continue
        for src, proposal, target in CELLS:
            uid = "V-"+token("trial",family,src,proposal)
            cid = "J-"+token("case",family)
            tm = "2026-11-19T15:00:00+09:00"
            case = dict(case_id=cid, revision="r1", as_of=tm, request="原票に基づき、この案件の引き継ぎ本文を照合してください。",
                        scopes={"report":{"name":"引き継ぎ","checks":["原票照合"]},
                                "operation":{"name":"後続業務","checks":["実施記録"]}},records=[])
            for i, text in enumerate([r["record_"+src],*r["facts"]],1):
                case["records"].append(dict(case_id=cid,revision="r1",ref=f"E{i}",scope="report",check="原票照合",
                                            source="direct",result="met",at=tm,available_at=tm,text=text))
            extra = "".join(r["facts"])
            body = r["original"] + extra
            raw = json.dumps({"findings":[dict(sentence_id=1, quote=r["original"], replacement=r["candidate_"+proposal],
                                               reason="引き継ぎ本文と原票の関係を照合した。",checked_refs=["E1"])]},
                             ensure_ascii=False,sort_keys=True)
            trace = body_review.apply_review(case,body,raw)
            require(trace["status"]=="flagged" and trace["proposed_body"]==r["candidate_"+proposal]+extra
                    and candidate_check.build_prompt(case,body,raw), "invalid controlled candidate")
            units.append(dict(id=uid,case=case,body=body,r1_raw=raw))
            keys.append(dict(id=uid,family=family,source=src,proposal=proposal,expected=target))
    return sorted(units,key=lambda r:r["id"]), sorted(keys,key=lambda r:r["id"])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=["packet","lock","check","open"])
    args=p.parse_args()
    root=STUDY/"inputs"
    records=families()
    packet, expected=source_rows(records)
    publish(root/"source-packet.json",packet,args.action!="packet")
    if args.action=="packet":
        return
    audit=qualify(expected,[route.read_json(root/f"source-votes/{w}.json") for w in ("first","second")])
    units,keys=units_for(records,audit["selected"])
    for name,obj in [("source-audit.json",audit),("units.json",units),("key-sha256.json",hashlib.sha256(wire(keys)).hexdigest())]:
        publish(root/name,obj,args.action!="lock")
    if args.action in ("check","open"):
        publish(root/"key.json",keys,args.action=="check")
    print("Eligible",audit["eligible"],"selected",audit["selected"],"cases",len(units))


if __name__=="__main__":
    main()
