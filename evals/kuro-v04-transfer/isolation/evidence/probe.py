
import csv, errno, io, json, os, socket, sqlite3, zipfile
from pathlib import Path
rows = list(csv.DictReader(Path("/input/dispatch.csv").read_text().splitlines()))
assert rows == [{"ticket":"OFC-101", "team":"Facilities"}]
log = {"input_read":rows, "cwd":os.getcwd(), "input_visible":sorted(os.listdir("/input")),
       "env_names":sorted(os.environ), "root_entries":sorted(os.listdir("/"))}
assert sorted(os.environ) == ["HOME", "LANG", "PATH", "PWD"]
def denial(name, call, codes):
    try:
        call()
    except OSError as exc:
        assert exc.errno in codes, (name, exc)
        log[name] = {"errno":exc.errno, "error":exc.strerror}
    else:
        raise AssertionError(name + " unexpectedly succeeded")
for category, path in {'peer': '/workspace/scratch/ceaa355c859e/next-dmd/isolation/evidence/outside-peer/synthetic-marker.txt', 'key': '/workspace/scratch/ceaa355c859e/next-dmd/isolation/evidence/outside-key/synthetic-marker.txt', 'repo': '/workspace/scratch/ceaa355c859e/next-dmd/isolation/evidence/outside-repo/synthetic-marker.txt'}.items():
    denial(category + "_read", lambda: Path(path).read_text(), {errno.ENOENT})
denial("input_edit", lambda: Path("/input/dispatch.csv").write_text("changed"), {errno.EROFS})
denial("input_create", lambda: Path("/input/new").touch(), {errno.EROFS})
denial("runtime_write", lambda: Path("/usr/lib/worker-temp").touch(), {errno.EROFS})
denial("root_write", lambda: Path("/worker-temp").touch(), {errno.EROFS})
denial("proc_read", lambda: Path("/proc/self/environ").read_bytes(), {errno.ENOENT})
denial("network_socket", lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM), {errno.EPERM})
denial("unix_socket", lambda: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM), {errno.EPERM})
with zipfile.ZipFile(io.BytesIO(), "w", zipfile.ZIP_DEFLATED) as archive:
    archive.writestr("test.csv", "header")
assert sqlite3.connect(":memory:").execute("select 1").fetchone() == (1,)
Path("/delivery/observed.json").write_text(json.dumps(log, indent=2) + "\n")
print("allowed office-data read and delivery write, all denial assertions passed")
