"""Compare the interrupted wave with the complete repeat and account for observed usage."""
import argparse
import statistics
import subprocess
from pathlib import Path

import check_interruption
import live

CHECKPOINT = "7634ceca670b4bcafd27231a5df910814781f638"
RESULTS = live.STUDY / "results"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=live.REPO)


def check_archive():
    prefix = RESULTS.relative_to(live.REPO).as_posix()
    previous = f"{prefix}/live/review/"
    archive = RESULTS / "interrupted-wave/review"
    files = git("ls-tree", "-r", "--name-only", CHECKPOINT, previous).decode().splitlines()
    mapping = {archive / name.removeprefix(previous): name for name in files}
    actual = {path for path in archive.rglob("*") if path.is_file()}
    live.require(len(files) == 7 and set(mapping) == actual, "archived schedule and six claims required")
    for name in ("interruption.json", "known-ceiling.json"):
        mapping[RESULTS / name] = f"{prefix}/{name}"
    for path, name in mapping.items():
        live.require(path.read_bytes() == git("show", f"{CHECKPOINT}:{name}"), f"checkpoint differs: {name}")
    live.require((archive / "dispatch.json").read_bytes() == (RESULTS / "live/review/dispatch.json").read_bytes(),
                 "repeat review schedule differs")
    check_interruption.main()
    return live.read(RESULTS / "interruption.json")["rows"]


def comparison(first, repeat):
    keys = ("packet_sha256", "prompt_sha256")
    live.require(all(first[k] == repeat[k] for k in keys), "different input for repeat")
    before, after = first["trace"], repeat["trace"]
    def sentences(trace):
        return sorted({f["sentence_id"] for f in trace["findings"]})
    left, right = before["proposed_body"], after["proposed_body"]
    return {
        "unit_id": first["unit_id"],
        "first_flagged": before["status"] == "flagged",
        "repeat_flagged": after["status"] == "flagged",
        "first_sentence_ids": sentences(before),
        "repeat_sentence_ids": sentences(after),
        "same_candidate_utf8": isinstance(left, str) and isinstance(right, str)
                               and left.encode("utf-8") == right.encode("utf-8"),
    }


def usage(rows):
    totals = {}
    for key in ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                "output_tokens", "reasoning_output_tokens"):
        vals = [r[key] for r in rows]
        live.require(all(type(v) is int and v >= 0 for v in vals), "unexpected token usage")
        totals[key] = sum(vals)
    totals["total_tokens"] = totals["input_tokens"] + totals["output_tokens"]
    return totals


def metrics(rows):
    durations = [r["elapsed_ms"] for r in rows]
    return {
        "calls": len(rows),
        "token_usage": usage([r["usage"] for r in rows]),
        "median_call_ms": statistics.median(durations) if durations else None,
        "sum_call_ms": sum(durations),
        "first_start_to_last_finish_ms": round(
            (max(r["cli_finished_unix_ns"] for r in rows) - min(r["cli_started_unix_ns"] for r in rows)) / 1e6, 3
        ) if rows else None,
    }


def audit():
    first = check_archive()
    live.check()
    data, calls, comparisons = {}, [], []
    for stage in ("review", "verify"):
        for path in sorted((RESULTS / "live" / stage / "receipts").glob("*.json")):
            receipt = live.read(path)
            uid, meta = receipt["unit_id"], receipt["meta"]
            group = "novel" if uid in live.NEW_IDS else ("diagnostic" if uid == "A2948" else "previous")
            data.setdefault((stage, group), []).append(meta)
            calls.append(meta)
            if stage == "review":
                previous = next((r for r in first if r["unit_id"] == uid and r["task_complete"]), None)
                if previous:
                    comparisons.append(comparison(previous, receipt))

    for key in ("attempt_id", "session_id"):
        old_ids = {r[key] for r in first}
        new_ids = {r[key] for r in calls}
        live.require(len(old_ids) == 6 and len(new_ids) == len(calls) and not old_ids.intersection(new_ids),
                     f"ID collision across waves: {key}")
    live.require(len(comparisons) == 5, "expected five matched supplementary responses")

    reported = [r["tokens_when_reported"] for r in first if r["tokens_when_reported"] is not None]
    official = metrics(calls)
    supplementary = usage(reported)
    return {
        "first_wave_checkpoint": CHECKPOINT,
        "archived_review_claims": len(first),
        "wave1_and_repeat_ids_disjoint": True,
        "supplementary_outputs_compared": len(comparisons),
        "same_flag_count": sum(r["first_flagged"] == r["repeat_flagged"] for r in comparisons),
        "same_sentence_set_count": sum(r["first_sentence_ids"] == r["repeat_sentence_ids"] for r in comparisons),
        "same_candidate_utf8_count": sum(r["same_candidate_utf8"] for r in comparisons),
        "comparisons": comparisons,
        "scored_official_calls": official,
        "by_stage_and_cohort": {stage: {group: metrics(data.get((stage, group), [])) for group in groups}
                                for stage, groups in (("review", ("novel",)), ("verify", ("novel", "previous", "diagnostic")))},
        "supplementary_usage": {"recorded_calls": len(reported), "unreported_claims": len(first) - len(reported),
                                "token_usage": supplementary},
        "observed_tokens_across_waves_lower_bound": official["token_usage"]["total_tokens"] + supplementary["total_tokens"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = live.encode(audit())
    dest = RESULTS / "restart-audit.json"
    if args.write:
        dest.write_bytes(result)
    else:
        live.require(dest.read_bytes() == result, "restart audit differs")
    print("Archived first wave, disjoint attempts and sessions, five repeated texts and measured usage verified.")
