"""Build a cutoff-bound handoff review and validate optional text edits, separately from B1."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from . import route


PROMPT = Path(__file__).with_name("body_review.txt")
ROW_KEYS = ("ref", "case_id", "revision", "scope", "check", "at", "available_at", "source", "result", "text")
FINDING_KEYS = {"sentence_id", "quote", "reason", "checked_refs", "replacement"}
OPENERS = {"「": "」", "『": "』", "（": "）", "(": ")", "【": "】", "“": "”", "‘": "’", '"': '"'}
ENDS = "。！？!?"


def digest(value):
    wire = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))
    return hashlib.sha256(wire.encode("utf-8")).hexdigest()


def sentences(body):
    """Index spans in the original Unicode string. Whitespace between sentences remains untouched."""
    if not route.nonblank(body):
        raise ValueError("handoff text missing or blank")
    spans = []
    closers = []
    start = 0
    for i, ch in enumerate(body):
        if closers and ch == closers[-1]:
            closers.pop()
        elif ch in OPENERS:
            closers.append(OPENERS[ch])
        if closers:
            continue
        at_end = i + 1 == len(body)
        next_ch = body[i + 1:i + 2]
        if ch in ENDS and next_ch and next_ch in ENDS:
            continue
        if not (ch in ENDS or ch in "\r\n" or (ch == "." and (at_end or next_ch.isspace()))):
            continue
        spans.append((start, i + 1))
        start = i + 1
    spans.append((start, len(body)))
    result = []
    for start, end in spans:
        while start < end and body[start].isspace():
            start += 1
        while end > start and body[end - 1].isspace():
            end -= 1
        if start < end:
            result.append({"id": len(result) + 1, "start": start, "end": end, "text": body[start:end]})
    return result


def make_packet(case, body):
    indexed = sentences(body)
    if not isinstance(case, dict) or not route.nonblank(case.get("case_id")):
        raise ValueError("case must identify the original case_id")
    if not route.valid_revision(case.get("revision")) or not route.nonblank(case.get("request")):
        raise ValueError("case must supply a typed revision and request")
    cutoff = route.instant(case.get("as_of"))
    scopes = {kind: route.scope_spec(case, kind) for kind in route.SCOPES}
    rows = case.get("records")
    if not isinstance(rows, list):
        raise ValueError("records must be an array")

    visible = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("source registry contains a non-record")
        if (row.get("case_id") != case["case_id"] or type(row.get("revision")) is not type(case["revision"])
                or row["revision"] != case["revision"]):
            continue
        try:
            observed, available = (route.instant(row.get(k)) for k in ("at", "available_at"))
        except ValueError:
            continue
        if not observed <= available <= cutoff:
            continue
        if not any(row.get("scope") in (key, spec["name"]) and row.get("check") in spec["checks"]
                   for key, spec in scopes.items()):
            continue
        if row.get("source") not in ("direct", "reported") or row.get("result") not in ("met", "pending"):
            continue
        if not route.nonblank(row.get("ref")) or not route.nonblank(row.get("text")):
            continue
        visible.append({key: row[key] for key in ROW_KEYS})
    refs = [row["ref"] for row in visible]
    if len(set(refs)) != len(refs):
        raise ValueError("duplicate source reference in visible records")

    # Only fields with a defined interpretation enter the evidence packet.
    # The request identifies the work; a draft response is never a witness.
    source = {key: case[key] for key in ("case_id", "revision", "as_of", "request")}
    source["scopes"] = {kind: {"name": spec["name"], "checks": list(spec["checks"])}
                        for kind, spec in scopes.items()}
    source["records"] = visible
    return {**source, "source_sha256": digest(source), "original_body": body, "sentences": indexed}


def packet_sha256(case, body):
    return digest(make_packet(case, body))


def build_review_prompt(case, body):
    payload = make_packet(case, body)
    return PROMPT.read_text(encoding="utf-8") + "\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def locate(finding, indexed, refs):
    if not isinstance(finding, dict) or set(finding) != FINDING_KEYS:
        raise ValueError("unexpected finding schema")
    sid = finding["sentence_id"]
    if type(sid) is not int or not 1 <= sid <= len(indexed):
        raise ValueError("unknown sentence_id")
    quote, replacement = finding["quote"], finding["replacement"]
    if not route.nonblank(quote) or not isinstance(replacement, str) or replacement == quote:
        raise ValueError("provide an exact nonempty quote and a changed replacement")
    if not route.nonblank(finding["reason"]):
        raise ValueError("reason missing")
    cited = finding["checked_refs"]
    if (not isinstance(cited, list) or not all(route.nonblank(r) and r in refs for r in cited)
            or len(set(cited)) != len(cited)):
        raise ValueError("invalid checked_refs")
    sentence = indexed[sid - 1]
    local = sentence["text"].find(quote)
    if local < 0 or sentence["text"].find(quote, local + 1) != -1:
        raise ValueError("quote must match exactly once in its sentence")
    start = sentence["start"] + local
    return {**finding, "start": start, "end": start + len(quote)}


def apply_review(case, body, raw_review_text, *, expected_packet_sha256=None):
    """Return a proposal or an invalid receipt. Never partially apply an invalid response."""
    source = case if isinstance(case, dict) else {}
    result = {key: source.get(key) for key in ("case_id", "revision", "as_of")}
    result.update(source_sha256=None, packet_sha256=None, original_body=body, raw_review=raw_review_text,
                  sentences=[], status="invalid", errors=[], findings=[], proposed_body=None)
    try:
        packet = make_packet(case, body)
        result.update(source_sha256=packet["source_sha256"], packet_sha256=digest(packet),
                      sentences=packet["sentences"])
        if expected_packet_sha256 is not None and expected_packet_sha256 != result["packet_sha256"]:
            raise ValueError("review input packet digest mismatch")
        if not isinstance(raw_review_text, str):
            raise ValueError("review text missing")
        parsed = json.loads(raw_review_text, object_pairs_hook=route.unique_keys, parse_constant=route.invalid_constant)
        # A JSON escape may decode to an unpaired surrogate. UTF-8 receipts cannot publish it.
        json.dumps(parsed, ensure_ascii=False).encode("utf-8")
        if not isinstance(parsed, dict) or set(parsed) != {"findings"} or not isinstance(parsed["findings"], list):
            raise ValueError("expected a JSON object with a findings array")
        refs = {row["ref"] for row in packet["records"]}
        accepted = sorted((locate(f, packet["sentences"], refs) for f in parsed["findings"]),
                          key=lambda f: f["start"])
        cursor = 0
        parts = []
        for edit in accepted:
            if edit["start"] < cursor:
                raise ValueError("overlapping proposed edits")
            parts.extend([body[cursor:edit["start"]], edit["replacement"]])
            cursor = edit["end"]
        proposal = "".join([*parts, body[cursor:]])
        if not route.nonblank(proposal):
            raise ValueError("empty proposed handoff")
    except ValueError as exc:
        result["errors"] = [str(exc)]
        return result
    result.update(status="flagged" if accepted else "clear", findings=accepted, proposed_body=proposal)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prompt", "apply"])
    parser.add_argument("case", type=Path)
    parser.add_argument("handoff", type=Path, help="original UTF-8 text")
    parser.add_argument("review", type=Path, nargs="?", help="reviewer response JSON")
    parser.add_argument("--packet-sha256", help="input digest recorded at dispatch")
    args = parser.parse_args()
    try:
        case, body = route.read_json(args.case), args.handoff.read_bytes().decode("utf-8")
        if args.command == "prompt":
            sys.stdout.write(build_review_prompt(case, body))
            return
        if not args.review:
            parser.error("apply requires the review file")
        receipt = apply_review(case, body, args.review.read_bytes().decode("utf-8"),
                               expected_packet_sha256=args.packet_sha256)
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        if receipt["status"] == "invalid":
            raise SystemExit(2)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
