"""Generate the R1 prompt for a single review of a handoff.

From the repository root, generate the prompt and send it to the reviewer once:

    python3 -m integrations.evidence_handoff.consensus_review case.json handoff.txt

Save the reviewer's JSON response as review.json and apply it with the existing validator:

    python3 -m integrations.evidence_handoff.body_review apply case.json handoff.txt review.json
"""

import argparse
import sys
from pathlib import Path

from . import body_review, route


READING_INSTRUCTIONS = """原票の文に複数の自然な読み方があるときは、何が誰・どの対象に結び付くかを読み方ごとに確かめる。依頼と記録の全体を照合し、別の記録による明示や訂正も踏まえて、なお成り立つ読み方を絞る。原票が関係を明示している場合は、その具体性を保つ。

本文の断定が残った読み方の一部でしか成り立たないときは、その箇所を指摘する。訂正ではどの読み方でも裏付けられる事実を残し、別の読み方に決め打ちしない。同じ文の数量・時刻・出典など、独立に裏付けられる情報も残す。原文の引用、複数の可能性の併記、関係が特定できないという記述は、本文が実際に述べている範囲を照合し、原票と合えばそのまま通す。"""


def build_consensus_prompt(case, body):
    return READING_INSTRUCTIONS + "\n\n" + body_review.build_review_prompt(case, body)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("case", type=Path)
    parser.add_argument("handoff", type=Path, help="original UTF-8 text")
    args = parser.parse_args()
    try:
        case = route.read_json(args.case)
        body = args.handoff.read_bytes().decode("utf-8")
        sys.stdout.write(build_consensus_prompt(case, body))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
