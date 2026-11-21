"""Watch immediate files in one receiver's directory until the separate stop marker exists."""
import ctypes
import json
import os
from pathlib import Path
import select
import struct
import sys
import time

folder, stop_file = map(Path, sys.argv[1:])
mask_names = {
    0x1: "ACCESS", 0x2: "MODIFY", 0x4: "ATTRIB", 0x8: "CLOSE_WRITE",
    0x10: "CLOSE_NOWRITE", 0x20: "OPEN", 0x40: "MOVED_FROM",
    0x80: "MOVED_TO", 0x100: "CREATE", 0x200: "DELETE",
    0x400: "DELETE_SELF", 0x800: "MOVE_SELF", 0x4000: "Q_OVERFLOW",
}
libc = ctypes.CDLL(None, use_errno=True)
fd = libc.inotify_init1(os.O_NONBLOCK)
if fd < 0 or libc.inotify_add_watch(fd, os.fsencode(folder), sum(mask_names) & ~0x4000) < 0:
    raise OSError(ctypes.get_errno(), "inotify watch")

def emit(kind, **fields):
    print(json.dumps({"kind": kind, "ns": time.time_ns(), **fields}), flush=True)

emit("ready")
while True:
    if select.select([fd], [], [], 0.1)[0]:
        data = os.read(fd, 65536)
        pos = 0
        while pos < len(data):
            _, mask, _, size = struct.unpack_from("iIII", data, pos)
            name = os.fsdecode(data[pos + 16:pos + 16 + size].split(b"\0")[0])
            pos += 16 + size
            emit("event", name=name, events=[label for bit, label in mask_names.items() if bit & mask])
    elif stop_file.exists():
        break
emit("stopped")
os.close(fd)
