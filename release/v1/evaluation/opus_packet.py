"""Prepare one Opus prompt or process one return on the trusted operator machine."""
import argparse
from pathlib import Path
import re
import sys

from gpt_wave import (
    CASE_IDS, ONE_LINE, SKILL, SKILL_SHA, build_followup, build_prompt,
    encode, extract_program, packet_hash, read_json, sha,
)
from dummy_isolation import PINNED


def checked(path, digest):
    data = path.read_bytes()
    if sha(data) != digest:
        raise ValueError(f"Input differs from its preregistration: {path.name}")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "followup"])
    parser.add_argument("repo", type=Path, help="Pinned checkout for the shared runner and instruction.")
    parser.add_argument("staging", type=Path, help="Frozen input packets and commitments.json.")
    parser.add_argument("jobs", type=Path, help="Private Opus series assignment.")
    parser.add_argument("jobs_sha", help="Registered digest of this series assignment.")
    parser.add_argument("commitments_sha", help="Registered digest of commitments.json.")
    parser.add_argument("case", choices=CASE_IDS)
    parser.add_argument("arm", choices=["B", "C"])
    parser.add_argument("runs", type=Path, help="Operator-only output parent.")
    parser.add_argument("--dummy", action="store_true", help="Only use known synthetic dummy inputs.")
    args = parser.parse_args()

    repo = args.repo.resolve()
    checked(args.jobs, args.jobs_sha)
    commitments = args.staging / "commitments.json"
    checked(commitments, args.commitments_sha)
    frozen = read_json(commitments)
    if frozen["dummy"] != args.dummy:
        raise ValueError("Study/dummy mode mismatch.")
    row = read_json(args.jobs)[args.case]
    job, packet_id = row[args.arm], row["packet"]
    if any(not re.fullmatch(r"[A-Za-z0-9_-]+", value) for value in (job, packet_id)):
        raise ValueError("Invalid identifier.")
    expected, = [p["input_sha256"] for p in frozen["packets"] if p["packet"] == packet_id]
    packet = args.staging / "packets" / packet_id
    if packet_hash(packet) != expected:
        raise ValueError("Packet digest mismatch.")
    instruction = checked(repo / SKILL, SKILL_SHA).decode() if args.arm == "C" else ONE_LINE
    prompt = build_prompt(packet, instruction)
    folder = args.runs / job

    if args.action == "prepare":
        folder.mkdir(mode=0o700, parents=True, exist_ok=False)
        (folder / "prompt1.txt").write_text(prompt, encoding="utf-8")
        (folder / "binding.json").write_bytes(encode({
            "job": job, "packet_sha256": expected, "condition_sha256": sha(instruction.encode()),
            "prompt_sha256": sha(prompt.encode()), "dummy": args.dummy,
        }))
    else:
        checked(folder / "prompt1.txt", sha(prompt.encode()))
        raw = (folder / "raw-program.txt").read_text(encoding="utf-8")
        if not raw.strip():
            raise ValueError("Record empty model response as incomplete.")
        code = folder / "submission.py"
        for dep, digest in PINNED.items():
            checked(repo / dep, digest)
        sys.path.insert(0, str(repo / "evals/kuro-v04-transfer/isolation"))
        from run import run
        with code.open("x", encoding="utf-8") as stream:
            stream.write(extract_program(raw))
        result = run(packet, code, folder / "delivery", folder / "execution.json")
        if result["worker_net_ns"] is None or result["worker_net_ns"] == result["host_net_ns"]:
            raise ValueError("Worker network isolation could not be verified.")
        (folder / "prompt2.txt").write_text(build_followup(folder / "delivery", result),
                                            encoding="utf-8")
    print(folder / ("prompt1.txt" if args.action == "prepare" else "prompt2.txt"))


if __name__ == "__main__":
    main()
