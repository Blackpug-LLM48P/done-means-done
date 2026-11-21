"""Replay the frozen session packets and generated fixtures with the standard library."""

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


def read(path):
    return json.loads(path.read_bytes())


def serialize(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def check(condition, context):
    if not condition:
        raise ValueError(context)


def fixtures(root, origins):
    # Counts of each state per source, as fixed in the protocol.
    per_state = {"dev": {"dev": 3, "volume": 1}, "hold": {"holda": 2, "holdb": 2, "volume": 2}}
    phases = {}
    volume = {}
    seen = set()
    for phase, counts in per_state.items():
        cases, key, pairs = [read(root / "inputs" / f"{phase}-{name}.json")
                             for name in ("cases", "key", "pairs")]
        index = {case["id"]: case for case in cases}
        check(len(index) == len(cases) and index.keys() == key.keys(), f"{phase}: case/key IDs")
        check(seen.isdisjoint(index), f"{phase}: reused case ID")
        seen.update(index)
        check(Counter(i for pair in pairs for i in pair) == Counter(index.keys()), f"{phase}: pairs")
        for pair in pairs:
            check(len(pair) == 2 and len({origins[i] for i in pair}) == 1 and
                  {key[i]["state"] for i in pair} == {"open", "complete"}, f"{phase}: {pair}")
        expected = {(source, state): n for source, n in counts.items() for state in ("open", "complete")}
        check(Counter((origins[i], entry["state"]) for i, entry in key.items()) == expected,
              f"{phase}: state and source counts")
        phases[phase] = index, pairs
        volume[phase] = {
            "cases": [case for case in cases if origins[case["id"]] == "volume"],
            "key": {i: entry for i, entry in key.items() if origins[i] == "volume"},
            "pairs": [pair for pair in pairs if origins[pair[0]] == "volume"],
        }
    check(seen == origins.keys(), "origin ID coverage")
    return phases, volume


def verify_volume(method, volume):
    with TemporaryDirectory() as tmp:
        work = Path(tmp)
        for name in ("generate.py", "oracle.py"):
            shutil.copyfile(method / "volume" / name, work / name)
        subprocess.run([sys.executable, "-I", work / "generate.py"], cwd=work, check=True)
        for phase, subsets in volume.items():
            for name, subset in subsets.items():
                filename = f"{phase}-{name}.json"
                check((work / filename).read_bytes() == serialize(subset), f"generated {filename}")
        subprocess.run([sys.executable, "-I", work / "oracle.py"], cwd=work, check=True)


def verify_packets(root):
    design = root / "design"
    for line in (design / "input-freeze.sha256").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        check(sha256((root / name).read_bytes()).hexdigest() == digest, f"input freeze: {name}")
    phases, volume = fixtures(root, read(design / "origins.json"))
    verify_volume(root / "method", volume)
    sessions = read(design / "sessions.json")
    controls = read(design / "control-sessions.json")
    expected = read(design / "packet-hashes.json")
    check(sessions.keys().isdisjoint(controls) and expected.keys() == sessions.keys() | controls.keys(),
          "packet manifest coverage")

    base = (root / "../../skills/report-reality-check/SKILL.md").read_bytes()
    addition = (design / "proposal.txt").read_bytes()
    proposal = (design / "proposal-workflow.txt").read_bytes()
    marker = b"## Output\n"
    check(base.count(marker) == 1 and proposal == base.replace(marker, addition + b"\n" + marker),
          "proposal workflow differs from registered insertion")
    workflows = {"v04": base, "one": (design / "one.txt").read_bytes(), "proposal": proposal}
    reader = (design / "reader.txt").read_bytes()

    def check_packet(tag, arm, cases, instructions):
        files = {"workflow.txt": workflows[arm], "reader.txt": instructions, "cases.json": serialize(cases)}
        for name, data in files.items():
            check(sha256(data).hexdigest() == expected[tag][name], f"{tag}/{name}")
        check(files.keys() == expected[tag].keys(), f"{tag}: unexpected packet files")

    arms = {"dev": ("v04",), "hold": ("v04", "one", "proposal")}
    check(Counter((s["phase"], s["arm"]) for s in sessions.values()) ==
          {(phase, arm): 2 for phase, names in arms.items() for arm in names}, "main session design")
    for phase, names in arms.items():
        index, pairs = phases[phase]
        reference = None
        for arm in names:
            baskets = []
            for tag, session in sessions.items():
                if (session["phase"], session["arm"]) != (phase, arm):
                    continue
                ids = session["ids"]
                for pair in pairs:
                    check(len(set(ids).intersection(pair)) == 1, f"{tag}: twin allocation {pair}")
                check_packet(tag, arm, [index[i] for i in ids], reader)
                baskets.append(ids)
            check(Counter(i for ids in baskets for i in ids) == Counter(index.keys()),
                  f"{phase}/{arm}: case coverage")
            ordered = sorted(baskets)
            check(reference is None or ordered == reference, f"{phase}/{arm}: matched case order")
            reference = ordered

    check(Counter((c["target"], c["arm"]) for c in controls.values()) ==
          {(target, arm): 1 for target in ("audit", "delivery") for arm in ("v04", "proposal")},
          "control session design")
    for tag, control in controls.items():
        instructions = reader + (control["added_instruction"] + "\n").encode("utf-8")
        check_packet(tag, control["arm"], volume["dev"]["cases"], instructions)
    print(f"Verified {len(sessions)} main packets, {len(controls)} target controls, and both volume splits.")


if __name__ == "__main__":
    verify_packets(Path(__file__).resolve().parents[1])
