"""Submit a genuine model participant's exact text; this adapter does no inference.

Usage: python participant.py /absolute/exchange PHASE WORKER < exact-model-reply.txt
The fresh worker should read only PHASE.request.json, use its task and evidence,
then provide its independently generated output. Distinct roles require distinct workers.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("exchange", type=Path)
parser.add_argument("phase", choices=("compact", "after", "original"))
parser.add_argument("worker")
args = parser.parse_args()
req = args.exchange / (args.phase + ".request.json")
reply = args.exchange / (args.phase + ".reply.json")
content = sys.stdin.read()
if not content.strip() or reply.exists():
    raise SystemExit("Requires a nonempty fresh answer and an unpublished reply path")
packet = {"worker": args.worker, "request_sha256": hashlib.sha256(req.read_bytes()).hexdigest(), "text": content}
tmp = reply.with_suffix(".tmp")
tmp.write_text(json.dumps(packet, ensure_ascii=False) + "\n")
os.replace(tmp, reply)
