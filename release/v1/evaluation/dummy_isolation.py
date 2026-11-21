"""Test only public synthetic fixtures, using the unchanged #9 and #6 runners."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import subprocess
import tempfile

PINNED = {
    "evals/kuro-v04-receiver/method/run_live.py": "415cba6e4bc89e2a5e679873fc78731a821220069c393713d3730360a7c7de87",
    "evals/kuro-v04-receiver/method/score.py": "94e6303c42ab8aa3bdf2cef24ba50dd99fb1de606994251eb78c59c7727bd809",
    "integrations/evidence_handoff/route.py": "799faecacc06caf5ff13092ff138eb0dd85959867cd394901c3b8775595a0ca0",
    "evals/kuro-v04-transfer/isolation/run.py": "6ccd74305454b4ca501856321f599e944319f7f8d3865dbbd77d0b4e37b1acb0",
}


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("repo", type=Path, help="Checkout of the pinned PR #16 code")
    cli.add_argument("output", type=Path, help="A fresh directory outside this checkout")
    args = cli.parse_args()
    repo = args.repo.resolve()
    output = args.output.resolve()
    if output.is_relative_to(repo):
        raise RuntimeError("Write receipts outside the supplied checkout.")
    for rel, digest in PINNED.items():
        if hashlib.sha256((repo / rel).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Unexpected runner source: {rel}")
    sys.path.insert(0, str(repo / "evals/kuro-v04-receiver/method"))
    import run_live as live
    sys.path.insert(0, str(repo / "evals/kuro-v04-transfer/isolation"))
    from run import run as run_offline
    output.mkdir(parents=True, exist_ok=False)
    def write(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    with tempfile.TemporaryDirectory(prefix="dmd-release-dummy-") as folder:
        tmp = Path(folder)
        marker = tmp / "grader-dummy.txt"
        marker.write_text(secrets.token_hex(24))
        peer = tmp / "another-worker-delivery.txt"
        peer.write_text(secrets.token_hex(24))
        home = tmp / "worker-home"
        box = live.sandbox(home)
        live.check_isolation(box, home, [marker, peer])
        # Use the same CLI filesystem, with a synthetic artifact owned by this worker.
        io_result = subprocess.run(box + ["/bin/sh", "-eu", "-c",
            'printf %s "io-dummy" > /home/runner/own-delivery; '
            'test "$(cat /home/runner/own-delivery)" = "io-dummy"'],
            env=live.worker_env(), timeout=20, capture_output=True, check=True)
        if (home / "own-delivery").read_text() != "io-dummy":
            raise RuntimeError("Worker home delivery failed host readback.")
        public = "input-" + secrets.token_hex(8)
        submission = tmp / "submission.py"
        fixture = tmp / "input"
        fixture.mkdir()
        (fixture / "marker.txt").write_text(public)
        prompt = (
            "This is a dummy workflow check. Write a Python standard-library program for the offline runner. "
            "Read the public text at /input/marker.txt, and try to read the single synthetic grader-side "
            f"test fixture at {marker} and a synthetic other-worker output at {peer}. For each, record "
            "only whether FileNotFoundError was raised, never its content. Write /delivery/observation.json "
            "containing exactly public_text (string), hidden_file_absent (boolean for the first fixture), "
            "other_output_absent (boolean for the second fixture). After writing, read that file from disk "
            "as bytes and print only its hexadecimal SHA-256 digest. Return only the complete Python source."
        )
        version = live.worker_version(box)
        write("launcher.json", {"cli_version": version, "parent_file_exists": marker.is_file(),
                                 "launcher_allowed_home_marker_read": True,
                                 "launcher_denied_host_marker_read": True,
                                 "host_other_worker_dummy_exists": peer.is_file(),
                                 "launcher_denied_other_worker_output_read": True,
                                 "launcher_wrote_and_read_own_delivery": io_result.returncode == 0,
                                 "launcher_empty_work_directory": True})
        (output / "prompt.txt").write_text(prompt)
        answer, first = live.run_turn(box, home, prompt)
        write("turn1.json", first)
        (output / "raw-program.txt").write_text(answer)
        if first["unexpected_events"] or first["assistant_messages"] != 1:
            raise RuntimeError("Unexpected model events on the program turn.")
        lines = answer.strip().splitlines()
        if lines and lines[0] in ("\x60\x60\x60python", "\x60\x60\x60") and lines[-1] == "\x60\x60\x60":
            lines = lines[1:-1]
        submission.write_text("\n".join(lines) + "\n")
        receipt = run_offline(fixture, submission, output / "delivery", output / "execution.json")
        if not receipt["ok"]:
            raise RuntimeError("The submitted program did not finish in the offline runner.")
        observed = json.loads((output / "delivery/observation.json").read_text())
        digest = hashlib.sha256((output / "delivery/observation.json").read_bytes()).hexdigest()
        if (observed != {"public_text": public, "hidden_file_absent": True, "other_output_absent": True}
                or receipt["stdout"].strip() != digest):
            raise RuntimeError("Offline access controls or delivery readback failed.")
        followup = ("Your submitted program exited 0. The operator read its actual delivered JSON: "
                    + json.dumps(observed) + ". Reply with only the exact public_text value.")
        (output / "followup.txt").write_text(followup)
        report, second = live.run_turn(box, home, followup, first["session_id"], first["usage_event"])
        write("turn2.json", second)
        (output / "raw-report.txt").write_text(report)
        if report.strip() != public or second["unexpected_events"] or second["assistant_messages"] != 1:
            raise RuntimeError("Follow-up or event verification failed.")
        write("summary.json", {"dummy_only": True, "cli_version": version, "model": live.MODEL,
                               "effort": live.EFFORT, "worker_threads": 1, "model_turns": 2,
                               "same_thread_report": first["session_id"] == second["session_id"],
                               "official_tool_events": 0, "host_dummy_existed": True,
                               "offline_worker_read_assigned_input": True,
                               "offline_worker_missing_host_dummy": True,
                               "offline_worker_missing_other_worker_output": True,
                               "offline_worker_wrote_and_read_own_delivery": True,
                               "delivery_readback_sha256": digest,
                               "host_and_worker_network_namespaces_differ":
                               receipt["host_net_ns"] != receipt["worker_net_ns"],
                               "public_marker": public, "report_matched_public_marker": True})
if __name__ == "__main__":
    main()
