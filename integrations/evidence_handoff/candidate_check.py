"""Check an R1 text proposal against the original source, retaining the original handoff."""

import hashlib
import json

from . import body_review, route


INSTRUCTIONS = """依頼、判定時点の原票、元の引き継ぎ本文、変更候補を読み、候補を提示してよいか独立に判断してください。

最初に原票と依頼の全体から、元の本文が実際にどんな事実を断定しているか読んでください。元の本文に裏付けの足りない断定があり、変更の必要がある場合に限り、候補を評価してください。候補がその断定を解消し、裏付けのある具体的事実や依頼に必要な情報を保ち、他の未裏付けの断定を含まないと判断できれば approve とします。元の本文が妥当な場合、単なる言い換え、判断がつかない場合、または候補に問題が残る場合は hold とします。別の読みが可能なだけで元の本文が特定の読みを断定したと扱わないでください。資料が同時に支持しない複数の読みを、それぞれ確定した事実として扱わないでください。

JSONオブジェクト1個を返してください。キーは verdict（"approve" または "hold"）、rationale（判断理由）、checked_refs（照合した原票の ref の配列）の3つです。approve には照合した ref を少なくとも1件示してください。"""


def _inputs(case, body, r1_raw):
    trace = body_review.apply_review(case, body, r1_raw)
    if trace["status"] == "invalid":
        raise ValueError("invalid R1 review: " + ", ".join(trace["errors"]))
    if trace["status"] == "clear":
        return None
    if trace["proposed_body"] == body:
        raise ValueError("R1 flagged the original but proposed no change")
    source = body_review.make_packet(case, body)
    fields = ("ref", "scope", "check", "at", "available_at", "source", "result", "text")
    records = [{k: row[k] for k in fields} for row in source["records"]]
    return {"request": source["request"], "as_of": source["as_of"], "records": records,
            "original_body": body, "proposed_body": trace["proposed_body"]}


def _prompt(payload):
    return INSTRUCTIONS + "\n\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def build_prompt(case, body, r1_raw):
    """Return the verifier input only when R1 made a valid, material proposal."""
    try:
        payload = _inputs(case, body, r1_raw)
        return _prompt(payload) if payload is not None else None
    except (TypeError, ValueError, KeyError, RecursionError):
        return None


def _validate(raw, records):
    if not isinstance(raw, str):
        raise ValueError("verifier response is missing")
    parsed = json.loads(raw, object_pairs_hook=route.unique_keys, parse_constant=route.invalid_constant)
    if not isinstance(parsed, dict) or set(parsed) != {"verdict", "rationale", "checked_refs"}:
        raise ValueError("unexpected verifier fields")
    if parsed["verdict"] not in ("approve", "hold") or not route.nonblank(parsed["rationale"]):
        raise ValueError("invalid verdict or rationale")
    refs = parsed["checked_refs"]
    visible = {row["ref"] for row in records}
    if (not isinstance(refs, list) or not all(route.nonblank(ref) and ref in visible for ref in refs)
            or len(set(refs)) != len(refs) or (parsed["verdict"] == "approve" and not refs)):
        raise ValueError("invalid checked_refs")
    parsed["rationale"].encode("utf-8")
    return parsed


def decide(case, body, r1_raw, verifier_raw=None, *, expected_prompt_sha256=None):
    """Replay R1 and validate an independent response. Only an offer contains a changed text.

    A caller with a separate dispatch step can pass its stored SHA-256 of the UTF-8
    verifier prompt to detect mismatched input. No decision applies the text or changes B1.
    """
    result = {"outcome": "hold", "original_body": body, "offered_body": None,
              "verdict": None, "rationale": None, "checked_refs": [], "prompt_sha256": None, "error": None}
    try:
        payload = _inputs(case, body, r1_raw)
        if payload is None:
            if verifier_raw is not None or expected_prompt_sha256 is not None:
                raise ValueError("unexpected verification for a clear handoff")
            result["outcome"] = "pass_through"
            return result
        result["prompt_sha256"] = hashlib.sha256(_prompt(payload).encode("utf-8")).hexdigest()
        if expected_prompt_sha256 is not None and expected_prompt_sha256 != result["prompt_sha256"]:
            raise ValueError("verifier input does not match dispatch digest")
        vote = _validate(verifier_raw, payload["records"])
        result.update(vote)
        if vote["verdict"] == "approve":
            result.update(outcome="offer", offered_body=payload["proposed_body"])
    except (TypeError, ValueError, KeyError, RecursionError) as error:
        result["error"] = str(error)
    return result
