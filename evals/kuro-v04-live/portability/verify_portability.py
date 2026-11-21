"""Run from any directory. Usage: python3 -B verify_portability.py PATH_TO_DMD_REPO
Prints JSON. Requires Python 3.12+, git, Linux unshare/bwrap and the Codex executable.
No clone, fetch, model call, or product worktree write.
"""
import hashlib
import io
import json
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from codex_discovery import list_skills

REV = "583edeaa8e5708675d654d27f913348200601c3a"
HISTORICAL = "2fe38b0e0d94c3dc89adabc9146b145953fb467b"
PILOT = "0caf2b7737bf4acf02cf9cda3749c595611bfa8b"
FORWARD = "aa05400eb20258a03e9ff655d59dfb1fbf1edcfe"
NAME = "report-reality-check"
SKILL = f"skills/{NAME}"
HISTORY = "evals/reviews/2026-11-17-pr3"
REPO = Path(sys.argv[1]).resolve()


def git(*args):
    return subprocess.check_output(["git", "-C", str(REPO), *args])


def revision_file(revision, path):
    return git("show", f"{revision}:{path}")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def files(root):
    return {str(p.relative_to(root)): digest(p.read_bytes())
            for p in sorted(root.rglob("*")) if p.is_file()}


def historical():
    manifest = json.loads(revision_file(HISTORICAL, HISTORY + "/preservation.json"))
    preserved = []
    for entry in manifest["protected_original_files"]:
        if "KEY" in entry["path"]:
            continue
        observed = digest(revision_file(REV, entry["path"]))
        preserved.append(dict(path=entry["path"], observed_sha256=observed,
                              expected_sha256=entry["sha256"], matches=observed == entry["sha256"]))
    commits = {k: subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", k + "^{commit}"],
                                 capture_output=True).returncode == 0 for k in (PILOT, FORWARD)}
    return {"reference": HISTORICAL, "nonkey_protected": preserved,
            "historical_commits_available_in_local_object_store": commits}


def checks(install, work):
    # Run precisely the entry point advertised by the installed SKILL.md.
    argv = [sys.executable, "scripts/verify_quotes.py"]
    reply = subprocess.run(argv + ["--help"], cwd=install, capture_output=True, text=True)
    help_test = {"exit": reply.returncode, "contains": {marker: marker in reply.stdout for marker in
        ("--draft ID", "--allow-unquoted", "Exit 0", "Exit 1", "Exit 2", "version/alias", "201 IDs")}}
    help_test["pass"] = help_test["exit"] == 0 and all(help_test["contains"].values())
    record = "[S07] 受領済み。release v8 を開いた。変更点ゼロ。\n[D09] 総合承認のみ\n"
    proof = "[M20] 箱は到着した。\n"
    all_ids = "".join(f"[Z{i:03d}] observation {i}\n" for i in range(1, 203))
    table = "| # | 根拠 |\n| --- | --- |\n"
    rows = []
    outcomes = [
        ("alias JP, second file, uncited", ['S07「受領済み」、通常別名のv8で「変更点ゼロ」。',
                'M20: 「箱は到着した」', '「release v8」'], [record, proof], ["--draft", "D09"], 0,
         ["3 found in cited blocks; 1 found by whole-record search only.", "Draft exclusion: D09"]),
        ("alias EN in prior block", ['S07 "release v8" (alias v8) confirmed "変更点ゼロ"'], [record],
         [], 0, ["2 found in cited blocks"]),
        ("declared alias block takes precedence", ['S07「受領済み」、版名 v8に「変更点ゼロ」'],
         [record, "[v8] 後で変更あり\n"], [], 1, ["WRONG PLACE"]),
        ("version absent as exact token", ['S07「受領済み」、別名 v8 は「変更点ゼロ」'],
         [record.replace("v8 ", "v8.2 ")], [], 1, ["UNKNOWN ID"]),
        ("draft only no ID", ['「総合承認のみ」'], [record], ["--draft", "D09"], 1, ["DRAFT ONLY"]),
        ("draft ID not in source", ['S07「受領済み」'], [record], ["--draft", "D90"], 2, ["INPUT ERROR"]),
        ("duplicate ID across files", ['S07「受領済み」'], [record, "[S07] 転載"], [], 2, ["INPUT ERROR"]),
        ("201 ID range", ['Z001–Z201 "observation 201"'], [all_ids], [], 0, ["1 found in cited blocks"]),
        ("202 ID range", ['Z001–Z202 "observation 202"'], [all_ids], [], 1, ["INVALID ID"]),
        ("39 CJK characters", ['「' + "甲"*39 + '」'], ["甲"*39], [], 0, ["0 over the length rule"]),
        ("40 CJK characters", ['「' + "甲"*40 + '」'], ["甲"*40], [], 1, ["1 over the length rule"]),
        ("allow unquoted with positive quote", ['S07「受領済み」', "目視のみ"], [record],
         ["--allow-unquoted"], 0, ["Rows without a quote: 1"]),
        ("allow unquoted alone still fails", ["目視のみ"], [record], ["--allow-unquoted"], 1,
         ["No quotes found"]),
    ]
    for i, (title, cells, records, flags, code, terms) in enumerate(outcomes):
        case = work / str(i)
        case.mkdir()
        ledger = case / "受渡し 台帳.md"
        ledger.write_text(table + "".join(f"| {n} | {cell} |\n" for n, cell in enumerate(cells, 1)))
        paths = []
        for j, data in enumerate(records):
            path = case / f"作業 記録{j}.txt"
            path.write_text(data)
            paths.append(path)
        before = files(case)
        run = subprocess.run(argv + flags + [ledger, *paths], cwd=install,
                             capture_output=True, text=True)
        output = run.stdout + run.stderr
        rows.append({"name": title, "expected_exit": code, "exit": run.returncode,
                     "checks": {s: s in output for s in terms}, "stdout": run.stdout, "stderr": run.stderr,
                     "inputs_unchanged": before == files(case),
                     "pass": run.returncode == code and all(s in output for s in terms) and before == files(case)})
    return help_test, rows


def main():
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        archive = git("archive", REV, SKILL, HISTORY + "/replay-cases.json", HISTORY + "/replay.py")
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(work, filter="data")
        source = work / SKILL
        project = work / "fresh project"
        subprocess.run(["git", "init", "-q", project], check=True)
        before = list_skills(project)
        claude_install = project / ".claude/skills" / NAME
        shutil.copytree(source, claude_install)
        claude = {"on_path": shutil.which("claude") is not None,
                  "scope": "README project folder copy, frontmatter and relative resources",
                  "files": files(claude_install)}
        desc_line = (source / "SKILL.md").read_text().splitlines()[2].removeprefix("description: ")
        expected_files = {"SKILL.md", "DESIGN.md", "scripts/verify_quotes.py", "references/work-state-check.md"}
        skill_text = (claude_install / "SKILL.md").read_text()
        claude["pass"] = (files(source) == claude["files"] and set(claude["files"]) == expected_files
                          and f"name: {NAME}" in skill_text
                          and all(p in skill_text for p in ("scripts/verify_quotes.py", "references/work-state-check.md")))
        claude_only = list_skills(project)
        codex_install = project / ".agents/skills" / NAME
        shutil.copytree(source, codex_install)
        after = list_skills(project)
        target = after["candidate"]
        codex = {"empty_project": before, "claude_path_only": claude_only, "after": after, "action": "skills/list only",
                 "pass": not before["candidate"] and not before["errors"] and not after["errors"]
                 and not claude_only["candidate"] and not claude_only["errors"]
                 and len(target) == 1 and target[0]["enabled"] and target[0]["scope"] == "repo"
                 and target[0]["description"] == desc_line
                 and target[0]["path"] == f"/project/.agents/skills/{NAME}/SKILL.md"}
        help_test, cli = checks(claude_install, work)
        replay = subprocess.run([sys.executable, "-B", work / HISTORY / "replay.py",
                                 "--script", claude_install / "scripts/verify_quotes.py"],
                                capture_output=True, text=True, check=True)
        replay_rows = json.loads(replay.stdout)
        preservation = historical()
        result = {
            "revision": REV, "python": platform.python_version(),
            "readme_claude_project_copy": claude, "codex_host_discovery": codex,
            "help": help_test, "cli": cli, "historical": preservation,
            "historical_cli_replay": {"reference": HISTORICAL, "cases": len(replay_rows),
                "matched_exit": sum(r["matched"] for r in replay_rows),
                "case_file_unchanged_since_reference": revision_file(REV, HISTORY + "/replay-cases.json")
                    == revision_file(HISTORICAL, HISTORY + "/replay-cases.json")},
            "package_bytes_unchanged_after_cli": files(claude_install) == files(source),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(not (claude["pass"] and codex["pass"] and help_test["pass"] and
                   all(r["pass"] for r in cli) and all(r["matched"] for r in replay_rows) and
                   all(r["matches"] for r in preservation["nonkey_protected"]) and
                   result["historical_cli_replay"]["case_file_unchanged_since_reference"] and
                   result["package_bytes_unchanged_after_cli"]))


if __name__ == "__main__":
    sys.exit(main())
