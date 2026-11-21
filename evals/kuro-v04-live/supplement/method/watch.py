"""Record opens of the presented skill files. Run from the supplement folder."""
import ctypes
import os
from pathlib import Path
import select
import struct
import time

base = Path("work/catalog/report-reality-check")
files = [base / "SKILL.md", base / "references/work-state-check.md"]
libc = ctypes.CDLL(None, use_errno=True)
fd = libc.inotify_init1(os.O_NONBLOCK)
if fd < 0:
    raise OSError(ctypes.get_errno(), "inotify_init1")
names = {}
for file in files:
    wd = libc.inotify_add_watch(fd, os.fsencode(file), 0x20)
    if wd < 0:
        raise OSError(ctypes.get_errno(), str(file))
    names[wd] = file.relative_to(base).as_posix()
print("ready", flush=True)
while True:
    if not select.select([fd], [], [], 1)[0]:
        continue
    payload = os.read(fd, 8192)
    pos = 0
    while pos < len(payload):
        wd, mask, _, size = struct.unpack_from("iIII", payload, pos)
        pos += 16 + size
        print(time.time_ns(), names.get(wd, "other"), hex(mask), flush=True)
