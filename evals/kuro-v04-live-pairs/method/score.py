"""Prepare blind candidate packets, resolve independent votes and replay the paired score."""
import argparse
from pathlib import Path
import re
import runpy
import secrets
import subprocess
import sys

STUDY = Path(__file__).resolve().parents[1]
RESULTS = STUDY / "results"
sys.path.insert(0, str(STUDY.parents[1]))
from integrations.evidence_handoff import body_review, candidate_check, route

prior = runpy.run_path(str(STUDY.parent / "kuro-v04-candidate/method/blind.py"))
require, encode, seal = (prior[k] for k in ("require", "encode", "seal"))
read_ballot = prior["ballots"].read_ballot
FIELDS = ("supported", "preserves_specifics", "fact_1", "fact_2")


def indexed(name):
    rows = route.read_json(STUDY / "inputs" / name)
    result = {u["id"]: u for u in rows}
    require(len(result) == len(rows) == 12, "expected twelve unique inputs")
    return result


def receipts(stage):
    folder = RESULTS / "live" / stage / "receipts"
    return {p.stem: route.read_json(p) for p in folder.glob("*.json")}


def inputs_and_observations():
    units, keys = indexed("units.json"), indexed("key.json")
    reviews, checks = receipts("review"), receipts("verify")
    require(units.keys() == keys.keys() == reviews.keys(), "incomplete R1 measurement")
    events, packets = {}, {}
    for uid, unit in sorted(units.items()):
        case, body, key = unit["case"], unit["body"], keys[uid]
        require(key["needs_repair"] == (key["source"] != "a"), "original label differs")
        review = reviews[uid]
        transport = review["meta"]["status"]
        raw = review["raw"] if transport == "ok" else None
        trace = body_review.apply_review(case, body, raw)
        require(trace == review["trace"], f"{uid}: R1 trace mismatch")
        prompt = candidate_check.build_prompt(case, body, raw)
        observation = trace["status"]
        if transport != "ok":
            observation = "missing"
        elif observation == "flagged" and prompt is None:
            observation = "invalid"
        check = checks.pop(uid, None)
        require((check is not None) == (prompt is not None), f"{uid}: verifier coverage")
        verdict = "uncalled"
        if check is not None:
            rows = body_review.make_packet(case, body)["records"]
            packets[uid] = {"records": [{k: row[k] for k in ("ref", "text")} for row in rows],
                            "request": case["request"], "original": body, "candidate": trace["proposed_body"],
                            "facts": key["facts"]}
            ok = check["meta"]["status"] == "ok"
            decision = candidate_check.decide(case, body, raw, check["raw"] if ok else None,
                                              expected_prompt_sha256=check["prompt_sha256"])
            require(check["trace"] == decision, f"{uid}: verification trace mismatch")
            verdict = (decision["verdict"] or "invalid") if ok else "missing"
        events[uid] = {"unit_id": uid, "family": key["family"], "source": key["source"],
                       "needs_repair": key["needs_repair"], "r1": observation, "verifier": verdict,
                       "changed_sentences": sorted({f["sentence_id"] for f in trace["findings"]})}
    require(not checks, "unexpected verifier receipt")
    return events, packets


def blind_packets(packets, create):
    path = RESULTS / "reader-aliases.json"
    if create and not path.exists():
        aliases = {"T-" + secrets.token_hex(16): {"unit_id": uid, "sha256": body_review.digest(row)}
                   for uid, row in packets.items()}
        require(len(aliases) == len(packets), "alias collision")
        seal(path, encode(aliases))
    aliases = route.read_json(path)
    require(len(aliases) == len(packets) and {v["unit_id"] for v in aliases.values()} == packets.keys(),
            "blinded packet coverage")
    rows = {}
    for label, link in sorted(aliases.items()):
        row = packets[link["unit_id"]]
        require(re.fullmatch(r"T-[0-9a-f]{32}", label) and body_review.digest(row) == link["sha256"],
                "blinded packet binding mismatch")
        rows[label] = row
    return aliases, rows


def first_vote(path, labels):
    blob, votes = read_ballot(path) if labels or path.exists() else (encode({}), {})
    require(isinstance(votes, dict) and votes.keys() == labels.keys(), f"{path.name}: alias coverage")
    normalized = {}
    for label, record in votes.items():
        require(isinstance(record, dict) and set(record) == {"supported", "preserves_specifics", "facts", "reason"}
                and isinstance(record["facts"], list) and len(record["facts"]) == 2
                and route.nonblank(record["reason"]), f"{path.name}/{label}: invalid vote schema")
        values = [record["supported"], record["preserves_specifics"], *record["facts"]]
        require(all(type(value) is bool for value in values), f"{path.name}/{label}: expected booleans")
        normalized[label] = dict(zip(FIELDS, values))
    return blob, normalized


def read_third(path, disputes):
    blob, votes = read_ballot(path) if disputes or path.exists() else (encode({}), {})
    require(isinstance(votes, dict) and votes.keys() == disputes.keys(), "arbitration coverage")
    for label, record in votes.items():
        fields = disputes[label]["disputed_fields"]
        require(isinstance(record, dict) and set(record) == {*fields, "reason"}
                and route.nonblank(record["reason"]) and all(type(record[f]) is bool for f in fields),
                f"{label}: only disputed fields and a reason may be arbitrated")
    return blob, votes


def ballots(mode, dest, aliases, packet):
    public = RESULTS / "reader-ballots"
    folder = public if mode == "check" else dest
    if mode != "check":
        require((dest / "packet.json").read_bytes() == encode(packet), "reader packet changed")
    votes = []
    for name in ("first.json", "second.json"):
        blob, normalized = first_vote(folder / name, packet)
        if mode == "disputes":
            seal(public / name, blob)
        else:
            require((public / name).read_bytes() == blob, f"{name}: reader ballot changed")
        votes.append(normalized)
    disputes = {}
    for label in packet:
        fields = [k for k in FIELDS if votes[0][label][k] != votes[1][label][k]]
        if fields:
            disputes[label] = {**packet[label], "disputed_fields": fields}
    if mode == "disputes":
        seal(dest / "disputes.json", encode(disputes))
        print(f"{len(disputes)} disputed candidates")
        return None
    if mode == "finalize":
        require((dest / "disputes.json").read_bytes() == encode(disputes), "arbitration packet changed")
    blob, third = read_third(folder / "third.json", disputes)
    if mode == "finalize":
        seal(public / "third.json", blob)
    require({p.name for p in public.glob("*.json")} == {"first.json", "second.json", "third.json"},
            "unexpected ballot files")
    grades = {}
    for label, link in aliases.items():
        values = votes[0][label].copy()
        fields = disputes.get(label, {}).get("disputed_fields", [])
        values.update({k: third[label][k] for k in fields})
        grades[link["unit_id"]] = {"alias": label, "criteria": values, "arbitrated_fields": fields}
    return grades


def classify(row, grade):
    target = row["needs_repair"]
    if row["r1"] == "flagged":
        require(grade is not None, "missing candidate grade")
        good = target and row["changed_sentences"] == [1] and all(grade["criteria"].values())
        alone = "correct_repair" if good else "wrong_offer"
        verdict = row["verifier"]
        gated = alone if verdict == "approve" else {
            "hold": "explicit_hold", "invalid": "invalid_response", "missing": "missing_response"}[verdict]
        return {**row, "grade": grade, "candidate_good": good, "r1_only": alone, "with_verifier": gated}
    require(grade is None, "unexpected candidate grade")
    result = {"clear": "missed_repair" if target else "correct_pass",
              "invalid": "invalid_response", "missing": "missing_response"}[row["r1"]]
    return {**row, "grade": None, "candidate_good": None, "r1_only": result, "with_verifier": result}


def rate(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "rate": numerator / denominator if denominator else None}


def summarize(rows):
    needed = sum(r["needs_repair"] for r in rows)
    bad = [r for r in rows if r["candidate_good"] is False]
    good = [r for r in rows if r["candidate_good"] is True]
    def verdict_count(items, verdict):
        return sum(r["verifier"] == verdict for r in items)
    result = {"cases": len(rows), "needs_repair": needed, "clean": len(rows) - needed,
              "r1_clear_missed": rate(sum(r["r1_only"] == "missed_repair" for r in rows), needed),
              "candidates": len(good) + len(bad), "good_candidates": len(good), "bad_candidates": len(bad),
              "bad_candidates_stopped": rate(verdict_count(bad, "hold"), len(bad)),
              "bad_candidates_approved": verdict_count(bad, "approve"),
              "good_candidates_held": rate(verdict_count(good, "hold"), len(good)),
              "r1_invalid": sum(r["r1"] == "invalid" for r in rows),
              "r1_missing": sum(r["r1"] == "missing" for r in rows),
              "verifier_invalid": verdict_count(rows, "invalid"), "verifier_missing": verdict_count(rows, "missing")}
    for arm in ("r1_only", "with_verifier"):
        counts = {name: sum(r[arm] == name for r in rows) for name in
                  ("correct_pass", "correct_repair", "wrong_offer", "missed_repair",
                   "explicit_hold", "invalid_response", "missing_response")}
        require(sum(counts.values()) == len(rows), "unclassified action")
        overedit = sum(not r["needs_repair"] and r[arm] == "wrong_offer" for r in rows)
        result[arm] = {**counts, "clean_pass": rate(counts["correct_pass"], len(rows) - needed),
                       "clean_overediting_offered": overedit, "repairs_offered": rate(counts["correct_repair"], needed),
                       "correct_automatic_resolution": counts["correct_repair"] + counts["correct_pass"]}
    return result


def run(mode, dest):
    subprocess.run([sys.executable, "-B", STUDY / "method/live.py", "--check"], check=True)
    if mode == "prepare":
        # Both sealed stage indices must be tracked; untracked or edited evidence invalidates the seal.
        subtree = "results/live"
        subprocess.run(["git", "ls-files", "--error-unmatch", f"{subtree}/review/runs.json",
                        f"{subtree}/verify/runs.json"], cwd=STUDY, check=True, stdout=subprocess.DEVNULL)
        dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all", "--", subtree],
                                        cwd=STUDY)
        require(not dirty, "commit the complete ungraded receipts first")
    events, packets = inputs_and_observations()
    aliases, packet = blind_packets(packets, mode == "prepare")
    if mode == "prepare":
        seal(dest / "packet.json", encode(packet))
        print(f"{len(packet)} blinded candidates")
        return
    grades = ballots(mode, dest, aliases, packet)
    if grades is None:
        return
    rows = [classify(e, grades.get(uid)) for uid, e in events.items()]
    by_source = {s: summarize([r for r in rows if r["source"] == s]) for s in ("a", "ambiguous", "b")}
    require(all(row["cases"] == 4 for row in by_source.values()), "source coverage")
    outputs = {"events.json": rows, "summary.json": {"overall": summarize(rows), "by_source": by_source,
               "reader_agreement": {"candidates": len(grades),
               "fully_agreed": sum(not g["arbitrated_fields"] for g in grades.values())}}}
    for name, data in outputs.items():
        path = RESULTS / name
        if mode == "finalize":
            seal(path, encode(data))
        else:
            require(path.read_bytes() == encode(data), f"{name}: replay differs")
    print(f"{len(rows)} paired cases, {len(packet)} live candidates graded")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    for action in ("prepare", "disputes", "finalize"):
        actions.add_argument("--" + action, type=Path, metavar="DEST")
    actions.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for action, value in vars(args).items():
        if value:
            run(action, None if action == "check" else value)
