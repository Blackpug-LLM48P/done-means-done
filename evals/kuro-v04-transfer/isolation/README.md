# Offline submission worker

A trusted operator selects one input directory and one model-authored Python file. The launcher copies both, creates a new Linux network namespace, and executes the file inside a separate Bubblewrap filesystem, PID, user, IPC and UTS namespace. The interpreter starts in isolated mode with site packages disabled. A private filesystem root contains the system Python standard library, its dynamic dependencies, the single submission, the assigned input, and an empty delivery directory. The root and input mounts are read only. The worker can write files under `/delivery` and print to captured streams. It inherits four fixed environment variables, including Bubblewrap's working directory. Host home, credentials, other jobs, repository, process filesystem and local service sockets are absent.

The public interface requires two fresh output paths. The Python submission executes at module scope, takes no arguments, reads from `/input`, and writes deliverables in `/delivery`. The working directory is `/delivery`.

```sh
python3 run.py --input assigned-files --code submission.py \
  --output run-A/delivery --receipt run-A/receipt.json
```

The receipt records SHA-256 hashes for individual filenames, the submitted program, captured stdout and stderr (first 16 KiB each), worker exit status, elapsed time, timeout flag, and host and worker network namespace IDs. IDs are observed on the same run and may be reused later by the kernel. The default wall-time budget is 25 seconds. `--timeout` accepts 1 through 180 seconds. A per-file limit of 32 MiB, a 768 MiB virtual memory limit, and per-process CPU and descriptor limits apply. The output directory remains available for inspection after a failed run. A delivery containing a nonregular entry fails output validation.

## Reproduce the controls

```sh
python3 -B verify.py /tmp/fresh-worker-verification --cli-diagnostic
```

The control reads a synthetic office CSV, checks ZIP and SQLite standard-library operations, and writes the observations to a JSON deliverable. The host reads three synthetic markers representing another submission, an answer key, and a repository. The worker attempts to open each by its absolute host path. Other assertions cover input and root writes, process-environment reads, and opening internet and UNIX-domain sockets. The filter prevents creation of new network endpoints. Unnamed local socket pairs remain available for process signal handling. See `evidence/summary.json`, `evidence/receipt.json`, and `evidence/delivery/observed.json` for the recorded run.

With the diagnostic flag, the verifier adds the installed Codex binary, a fixed executable-name symlink and a null device. Its temporary home is empty. Two receipts record the binary's version and the result of starting its supported Ollama inference mode. These diagnostic additions are confined to those two invocations.

## Scope of the measured boundary

The isolated process runs the authored Python file. Model inference and prompt delivery happen separately. This runner records actual access by the execution phase. It cannot attest to the ChatGPT model's tool permissions, host access, prompt history, or a live model interaction during execution. The control uses synthetic marker files and never needs account credentials.

The launcher requires Linux, Bubblewrap with `--disable-userns` and `--seccomp`, util-linux `unshare`, libseccomp, glibc `ldd`, system Python 3.11+, and an environment permitting unprivileged user and network namespaces. It fails if namespace setup fails. The operator supplies a curated input directory containing regular files and directories.
