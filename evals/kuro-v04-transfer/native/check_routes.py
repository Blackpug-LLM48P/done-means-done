"""Print a sanitized diagnostic for the alternative native Codex routes."""

import argparse
import json
import os
import subprocess
import tempfile


def run(args, **kwargs):
    return subprocess.run(
        ["codex", *args], capture_output=True, text=True, stdin=subprocess.DEVNULL,
        timeout=40, **kwargs,
    )


def diagnostic(process):
    message = (process.stdout + "\n" + process.stderr).lower()
    phrases = {
        "read_only_filesystem": "read-only file system (os error 30)",
        "operation_not_permitted": "operation not permitted (os error 1)",
        "app_server_init_failed": "failed to initialize in-process app-server client",
        "control_socket_unreachable": "failed to connect to",
        "keyring_load_failed": "failed to load cli auth from keyring",
        "not_logged_in": "not logged in",
    }
    return {
        "exit": process.returncode,
        "diagnostics": [name for name, text in phrases.items() if text in message],
    }


def check_store(store):
    with tempfile.TemporaryDirectory(prefix="dmd-auth-store-") as fresh:
        env = {**os.environ, "CODEX_HOME": fresh}
        return diagnostic(run(["-c", f'cli_auth_credentials_store="{store}"',
                               "login", "status"], env=env))


def check_model_startup():
    with tempfile.TemporaryDirectory(prefix="dmd-model-startup-") as fresh:
        temp_value = json.dumps(fresh)
        result = run([
            "exec", "--ignore-user-config", "--ephemeral", "--json",
            "--skip-git-repo-check", "-s", "read-only", "-m", "gpt-6.2-astra",
            "-c", "sqlite_home=" + temp_value, "-c", "log_dir=" + temp_value,
            "-c", 'history.persistence="none"', "--disable", "shell_snapshot",
            "Without any tools, reply exactly DMD-READY.",
        ], cwd=fresh)
    events = []
    for line in result.stdout.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            events.append(record)
    reports_ready = any(
        (row.get("item") or {}).get("text") == "DMD-READY" for row in events
    )
    return {**diagnostic(result), "event_count": len(events),
            "expected_reply_observed": reports_ready}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--try-model-startup", action="store_true",
                        help="Try a synthetic, one-reply turn through the existing CLI login")
    args = parser.parse_args()
    report = {
        "cli": run(["--version"]).stdout.strip(),
        "daemon_version": diagnostic(run(["app-server", "daemon", "version"])),
        "isolated_credential_stores": {s: check_store(s) for s in ["keyring", "ephemeral"]},
        "ambient_plan_token_variables_set": {
            var: bool(os.environ.get(var)) for var in ["ACCESS_TOKEN", "CODEX_ACCESS_TOKEN"]
        },
    }
    if args.try_model_startup:
        report["existing_login_model_startup"] = check_model_startup()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
