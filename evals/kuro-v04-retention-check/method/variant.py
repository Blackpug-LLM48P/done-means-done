"""A one-paragraph intervention; both arms use the existing verifier decision parser."""
from hashlib import sha256

from integrations.evidence_handoff import candidate_check


RETENTION = (
    "元の本文から断定を外した箇所を原票と照合してください。関係の結び方が複数通りに読めるときは、"
    "どの読みでも成り立つ具体的な情報が候補に残っているかを確かめ、それまで失われていれば hold とします。"
    "原票が裏付けない情報を取り除くことや、同じ情報を別の表現で伝えることは認めます。"
)


def build_prompt(case, body, r1_raw, arm):
    original = candidate_check.build_prompt(case, body, r1_raw)
    if original is None:
        raise ValueError("expected a material candidate for independent verification")
    if arm == "old":
        return original
    if arm != "new":
        raise ValueError("unknown verifier arm")
    instructions, separator, schema = candidate_check.INSTRUCTIONS.rpartition("\n\n")
    if not separator or not original.startswith(candidate_check.INSTRUCTIONS + "\n\n"):
        raise ValueError("unexpected verifier instruction layout")
    return instructions + separator + RETENTION + separator + schema + original[len(candidate_check.INSTRUCTIONS):]


def decide(case, body, r1_raw, raw, arm, expected_prompt_sha256):
    prompt = build_prompt(case, body, r1_raw, arm)
    digest = sha256(prompt.encode()).hexdigest()
    if digest != expected_prompt_sha256:
        raise ValueError("dispatch prompt digest differs from verifier arm")
    baseline = build_prompt(case, body, r1_raw, "old")
    result = candidate_check.decide(case, body, r1_raw, raw, expected_prompt_sha256=sha256(baseline.encode()).hexdigest())
    # The production parser binds its baseline input. Record the digest actually dispatched after checking both.
    result["prompt_sha256"] = digest
    return result
