"""Read-only integrity replay of the public synthetic packets and exact outputs."""
import hashlib
import json
from pathlib import Path

from score import score

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE / name).read_text())


def h(data):
    return hashlib.sha256(data).hexdigest()


def verify():
    case = read("case.json")
    obs = read("observation.json")
    saved_scores = read("scores.json")
    phases = ("compact", "after", "original")
    requests = {p: read(f"packets/{p}.request.json") for p in phases}
    replies = {p: read(f"packets/{p}.reply.json") for p in phases}
    rows = {r["phase"]: r for r in obs["provider_requests"]}
    assert obs["status"] == "all transport checks passed" and all(obs["checks"].values())
    for name, digest in obs["preregistered_sha256"].items():
        assert digest == h((HERE / name).read_bytes())
    for phase in phases:
        req = requests[phase]
        reply = replies[phase]
        result = obs["model_outputs"][phase]
        row = rows[phase]
        assert set(req) == {"task", "evidence"}
        assert result["text"] == reply["text"] and reply["worker"] == result["worker"]
        assert row["received_at"] <= row["dispatched_at"] <= result["received_at"]
        assert h((HERE / f"packets/{phase}.request.json").read_bytes()) == reply["request_sha256"] == row["worker_request_sha256"]
        assert h(result["text"].encode()) == result["sha256"]
        assert h(req["task"].encode()) == row["task_sha256"]
        assert h(req["evidence"].encode()) == row["evidence_sha256"]
    assert requests["compact"] == {"task": case["compact_task"], "evidence": case["record"]}
    assert requests["after"] == {"task": case["question"], "evidence": replies["compact"]["text"]}
    assert requests["original"] == {"task": case["question"], "evidence": case["record"]}
    assert obs["model_outputs"]["compact"]["received_at"] < rows["after"]["received_at"]
    for phase in ("original", "after"):
        assert score(replies[phase]["text"], case["frozen_answers"]) == saved_scores[phase]
    blind = read("source-review/input.json")
    ballot = read("source-review/review.json")["rows"]
    labels = read("workers.json")["participants"]["masked_source_review"]["condition_label_mapping"]
    assert blind["source"] == case["record"] and blind["original_question"] == case["question"]
    assert blind["answer_submissions"] == {label: replies[phase]["text"] for label, phase in labels.items()}
    assert len(ballot) == len(case["frozen_answers"])
    assert {row["field"]: row["expected"] for row in ballot} == case["frozen_answers"]
    assert all(row["source_quote"] and row["source_quote"] in case["record"] for row in ballot)
    assert all(row[label] == "supported" for row in ballot for label in labels)
    return True


if __name__ == "__main__":
    verify()
    print("Synthetic packets, returned bytes, source-to-handoff links, chronology, frozen scores and independent source ballot verified.")
