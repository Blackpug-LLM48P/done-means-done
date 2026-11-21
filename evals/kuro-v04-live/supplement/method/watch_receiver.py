"""Watch reads, writes, replacements, creation and removal in the small receiver folder."""
import ctypes
import os
from pathlib import Path
import select
import struct
import time

directory = Path("work/receiver")
libc = ctypes.CDLL(None, use_errno=True)
fd = libc.inotify_init1(os.O_NONBLOCK)
if fd < 0:
    raise OSError(ctypes.get_errno(), "inotify_init1")
codes = {1: "ACCESS", 2: "MODIFY", 4: "ATTRIB", 8: "CLOSE_WRITE", 32: "OPEN", 64: "MOVED_FROM", 128: "MOVED_TO", 256: "CREATE", 512: "DELETE"}
if libc.inotify_add_watch(fd, os.fsencode(directory), sum(codes)) < 0:
    raise OSError(ctypes.get_errno(), directory.as_posix())
print("ready", flush=True)
while True:
    if not select.select([fd], [], [], 1)[0]:
        continue
    payload = os.read(fd, 8192)
    pos = 0
    while pos < len(payload):
        _, mask, _, size = struct.unpack_from("iIII", payload, pos)
        name = os.fsdecode(payload[pos+16:pos+16+size].split(b"\0")[0])
        pos += 16 + size
        if name:
            print(time.time_ns(), name, "|".join(label for code,label in codes.items() if mask & code), flush=True)
