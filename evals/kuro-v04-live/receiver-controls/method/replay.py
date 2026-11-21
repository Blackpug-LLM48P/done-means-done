"""Verify the saved pair, summarize local observations, and display the model-coded outcomes."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
obs = root / "observations"

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

if digest(obs / "frozen.json") != "6c871d3218ceb8c047a4f49ff54dd609f814100f2e9950940af6c2b650d7ddab":
    raise ValueError("Frozen input manifest changed")
frozen = json.loads((obs / "frozen.json").read_text())
for name, expected in frozen.items():
    if digest(root / name) != expected:
        raise ValueError(f"Changed frozen input: {name}")

header = (root / "fixtures/header.txt").read_bytes() + b"\n"
body = (root / "fixtures/body.md").read_bytes()
if (obs / "r17.before.review.md").read_bytes() != body or (obs / "r52.before.review.md").read_bytes() != header + body:
    raise ValueError("The inputs differ beyond the header")
baseline_list = (root / "fixtures/archive-list.tsv").read_bytes()
write_events = {"MODIFY", "ATTRIB", "CLOSE_WRITE", "MOVED_FROM", "MOVED_TO", "CREATE", "DELETE", "DELETE_SELF", "MOVE_SELF"}
outcomes = json.loads((obs / "coding.json").read_text())
result = {}
for tag in ("r17", "r52"):
    template = (root / "fixtures/task.txt").read_text()
    prompt = (obs / f"{tag}.task.txt").read_text()
    folder = f"/workspace/scratch/ceaa355c859e/live-study/receiver-controls/work/{tag}"
    if prompt != template.replace("{folder}",folder):
        raise ValueError(f"Task mismatch: {tag}")
    raw_path = root / "raw" / f"{tag}.txt"
    if digest(raw_path) != outcomes[tag]["summary_sha256"]:
        raise ValueError(f"Response mismatch: {tag}")
    if (obs / f"{tag}.before.archive-list.tsv").read_bytes() != baseline_list:
        raise ValueError(f"Initial mock list mismatch: {tag}")
    log = [json.loads(line) for line in (obs / f"{tag}.events.jsonl").read_text().splitlines()]
    if log[0]["kind"] != "ready" or log[-1]["kind"] != "stopped":
        raise ValueError(f"Missing watch window: {tag}")
    events = [e for e in log if e["kind"] == "event"]
    if any("Q_OVERFLOW" in e["events"] for e in events):
        raise ValueError(f"Inotify overflow: {tag}")
    open_names = sorted({e["name"] for e in events if e["name"] and "OPEN" in e["events"]})
    accessed_names = sorted({e["name"] for e in events if e["name"] and "ACCESS" in e["events"]})
    byte_changes = [name for name in ["review.md", "archive-list.tsv"]
                    if digest(obs / f"{tag}.before.{name}") != digest(obs / f"{tag}.after.{name}")]
    result[tag] = {
        "header": tag == "r52",
        "open": open_names,
        "access": accessed_names,
        "write_events": [e for e in events if set(e["events"]) & write_events],
        "changed_files": byte_changes,
        "model_coding": outcomes[tag],
    }
print(json.dumps(result, ensure_ascii=False, indent=2))
