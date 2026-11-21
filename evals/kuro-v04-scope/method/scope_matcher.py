"""Evaluate lexical evidence selection with optional revision and action checks."""
import argparse
from collections import Counter
from dataclasses import dataclass
import json
from math import log1p
from pathlib import Path
import re
import unicodedata


def normalize(value):
    return unicodedata.normalize("NFKC", value).lower()


RUNS = re.compile(r"[a-z0-9]+|[ぁ-ゖァ-ヺー一-龯々]+")


def features(value):
    result = []
    for run in RUNS.findall(normalize(value)):
        if run.isascii() or len(run) == 1:
            result.append(run)
        else:
            result.extend(run[i:i + 2] for i in range(len(run) - 1))
    return result


class Lexicon:
    def __init__(self, rows):
        self.terms = [Counter(features(row["text"])) for row in rows]
        df = Counter()
        for terms in self.terms:
            df.update(terms.keys())
        self.idf = {term: log1p((len(rows) - freq + 0.5) / (freq + 0.5))
                    for term, freq in df.items()}
        total_length = sum(sum(terms.values()) for terms in self.terms)
        self.average_length = total_length / len(rows) if total_length else 1

    def score(self, terms, query):
        length_factor = 1.2 * (0.25 + 0.75 * sum(terms.values()) / self.average_length)
        return sum(self.idf[w] * terms[w] * 2.2 / (terms[w] + length_factor)
                   for w in sorted(query.intersection(terms)))


REV = re.compile(r"(?<![a-z0-9])(?P<prefix>revision|rev|r|version|ver|v)"
                 r"[.\s_-]*(?P<num>\d+(?:\.\d+)*)(?![a-z0-9])"
                 r"|第?\s*(?P<jp>\d+(?:\.\d+)*)\s*版")


def revisions(text):
    result = set()
    for match in REV.finditer(normalize(text)):
        if match["jp"]:
            result.add("v" + match["jp"])
        else:
            result.add(match["prefix"][0] + match["num"])
    return sorted(result)


# Each matcher needs affirmative evidence in a log. A bare action noun is insufficient.
# A query's claim may also use an action noun as its explicit request.
DONE = r"(?:を?(?:実施|実行|完了|確認)(?:した|しました|済(?:み)?|完了)?|済(?:み)?|完了|成功|ok|合格|した|しました|された|されました|できた|できました|を終えた)"
TEST = re.compile(r"(?:テスト|試験|pytest|unittest)")
HUMAN = re.compile(r"目視|肉眼|人手|手動|人の目|校正者")
ALL_PAGES = re.compile(r"全(?:\d+)?(?:ページ|頁|面)|全ての(?:ページ|頁|面)|すべての(?:ページ|頁|面)"
                       r"|各(?:ページ|頁)|\d+\s*(?:ページ|頁)(?:とも|すべて|全て|全件)"
                       r"|(?:全ページ|全頁)分")
PARTIAL = re.compile(r"(?:一部|抜(?:き|粋)|抜取|サンプル|先頭|最初|表紙|一枚目|1枚目)"
                     r"|(?:ページ|頁|枚)(?:だけ|のみ|に限)")
NO = re.compile(r"未(?:実施|実行|照合|校正|確認|検証|送信|受信|受領|着|達|開封|保存|完了|処理)"
                r"|(?:して|できて|されて|行って)(?:は)?(?:いな|おら|いませ)"
                r"|(?:行わ|実行し|照合し|比較し|受け取ら|送ら|開か|保存し|でき|され|せ)(?:なかっ|ない|ず)"
                r"|(?:読め|開け|でき)(?:ず|ない|なかった)|(?:ません|無かった)|(?:して|され)おらず"
                r"|(?:未|未だ)(?:送付|到着|点検|比較|検品|テスト|試験|判読|対応)|予定|見込み|計画|つもり|試み|試行中|(?:作業|処理)中|保留|中止|中断|失敗|エラー|未遂|見送|取りやめ"
                r"|(?:記録|証跡|実績|結果)(?:が|は)?(?:ない|なし|不明)|未だ|まだ.{0,12}ない"
                r"|(?:する|した)はず|(?:した|できた)(?:かどうか|かは不明)")
DISCOVERY_ONLY = re.compile(r"--collect-only|--collectonly|--co\b|--list-tests|dry[- ]run"
                            r"|(?:収集|列挙|検出|探索|一覧化|発見)(?:のみ|だけ)"
                            r"|(?:実行|実施)(?:件数)?[ :=はが]*(?:0|ゼロ)\s*(?:件|本|個|tests?)")
SPLIT = re.compile(r"[。！？!?;；\n、]+|(?<!\d),(?!\d)")
T = TEST.pattern
TEST_PASS = re.compile(r"全件通過|合格|全件成功|全て通過|すべて通過|が通った|(?<![0-9])[1-9]\d*\s+passed\b")


@dataclass(frozen=True)
class Rule:
    name: str
    mention: re.Pattern
    completed: re.Pattern


def rule(name, mention, completed):
    return Rule(name, re.compile(mention), re.compile(completed))


ACTIONS = (
    rule("open", r"開(?:い|け|く|き)|オープン|閲覧",
         r"開(?:いた|きました|けた|けました|ける(?:こと|状態)?(?:を確認)?|くことができた)|(?:オープン|閲覧)" + DONE + r"|閲覧可能"),
    rule("readable", r"可読|判読|読め|読み取",
         r"読め(?:た|ました|る(?:こと|状態)?(?:を確認)?)|判読(?:できた|可能)|可読(?:性を確認|を確認|性あり)"
         r"|読み取(?:れた|れました)"),
    rule("display", r"表示", r"表示(?:できた|された|を確認|成功|した)"),
    rule("proof", r"照合|突き合わ|突合|照らし合わ|校正|比較|見比べ|突きあわ|(?:目視|肉眼).{0,18}一致",
         r"(?:照合|突合|校正|比較)" + DONE
         + r"|(?:突き合わ|突きあわ|照らし合わ)せ(?:た|ました|済)|見比べ(?:た|ました)"
         r"|(?:目視|肉眼|照合|突合|原(?:本|稿)|台帳).{0,30}(?:一致|差異なし|相違なし)"),
    rule("receive", r"受領|受信|受け取|受けと|受取|着荷|到着|着信|届(?:い|き|く)",
         r"(?:受領|受信|受取|着荷|到着|着信)" + DONE
         + r"|(?:受け取|受けと)(?:った|りました|れた)|届(?:いた|きました)|受信(?:箱|側).{0,20}(?:着信|到着)(?:を確認)?"),
    rule("send", r"送信|送付|発送|送っ|送り|配信", r"(?:送信|送付|発送|配信)" + DONE
         + r"|送(?:った|りました)"),
    rule("test_run", T + r".{0,30}(?:実行|実施|走らせ|通過|合格|通っ|pass)|(?:\d+\s+(?:passed|failed)\b)",
         T + r".{0,36}(?:(?:実行|実施)" + DONE + r"|走らせ(?:た|ました)|を回した|が通った|に合格した|全件通過)"
         r"|(?<![\da-z])[1-9]\d*\s+(?:passed|failed)\b"),
    rule("test_discovery", r"収集|列挙|検出|探索|一覧化|発見|collect(?:ed|ion)?|--co\b|--list-tests",
         r"(?:収集|列挙|検出|探索|一覧化|発見)" + DONE
         + r"|(?:収集|列挙|検出)(?:のみ|だけ)(?:実行|実施|完了|した)|(?:--collect-only|--co\b|--list-tests).{0,12}実行" + DONE + r"|collected\s+[1-9]\d*\s+items?"),
    rule("save", r"保存|書き込|書込|格納|書き出|書出", r"(?:保存|書込|格納|書出)" + DONE
         + r"|書き込(?:んだ|みました)|書き出(?:した|しました)"),
)


def actions(text, *, request=False):
    """Map observed actions to co-located qualifiers. Preserve separate witnesses."""
    if request:
        affirmative = actions(text)
        if affirmative:
            return affirmative
    found = {}
    for piece in SPLIT.split(normalize(text)):
        if not piece or NO.search(piece):
            continue
        qualifiers = set()
        if HUMAN.search(piece):
            qualifiers.add("human")
        if ALL_PAGES.search(piece) and not PARTIAL.search(piece):
            qualifiers.add("all_pages")
        for action in ACTIONS:
            if action.name == "test_run" and DISCOVERY_ONLY.search(piece):
                continue
            if action.name == "test_discovery" and not (TEST.search(piece) or "collect" in piece):
                continue
            pattern = action.mention if request else action.completed
            if pattern.search(piece):
                relevant = qualifiers if action.name == "proof" else qualifiers - {"human"}
                if action.name == "test_run" and TEST_PASS.search(piece):
                    relevant = relevant | {"passed"}
                found.setdefault(action.name, []).append(sorted(relevant))
    return found


ARMS = {
    "source": (),
    "source_revision": ("revision",),
    "source_action": ("action",),
    "source_revision_action": ("revision", "action"),
}
POLICIES = ("veto", "rescue")
SOURCES = {"direct", "reported", "hearsay", "inference"}


def check_scope(row, target, gates):
    if row["source"] != "direct":
        return "source_" + row["source"]
    if "revision" in gates:
        if len(target["revisions"]) != 1:
            return "query_revision_missing_or_ambiguous"
        if row["revisions"] != target["revisions"]:
            return "revision_missing_ambiguous_or_mismatched"
    if "action" in gates:
        if not target["actions"]:
            return "query_action_unrecognized"
        for action, requirements in target["actions"].items():
            witnesses = row["actions"].get(action, [])
            if not witnesses:
                return "action_missing_or_unconfirmed:" + action
            required = set().union(*requirements)
            if not any(required.issubset(witness) for witness in witnesses):
                return "action_qualifier_missing:" + action
    return "eligible"


def require_keys(objects, keys, text_fields):
    ids = set()
    for obj in objects:
        if not isinstance(obj, dict) or not keys.issubset(obj):
            raise ValueError(f"Missing required fields: {sorted(keys)}")
        if any(not isinstance(obj[field], str) for field in text_fields):
            raise ValueError(f"Non-string field in: {sorted(text_fields)}")
        if not obj["id"] or obj["id"] in ids:
            raise ValueError(f"Missing or duplicate ID: {obj['id']!r}")
        ids.add(obj["id"])


def evaluate(cases):
    seen = set()
    for case in cases:
        cid = case["case_id"]
        if not isinstance(cid, str) or not cid or cid in seen:
            raise ValueError(f"Missing or duplicate case ID: {cid!r}")
        seen.add(cid)
        require_keys(case["rows"], {"id", "text", "source"}, {"id", "text", "source"})
        require_keys(case["queries"], {"id", "question", "claim"}, {"id", "question", "claim"})
        if any(row["source"] not in SOURCES for row in case["rows"]):
            raise ValueError(f"Unsupported source category in {cid}")
    lexicon = Lexicon([row for case in cases for row in case["rows"]])
    output = []
    offset = 0
    for case in cases:
        rows = [{"id": r["id"], "source": r["source"], "revisions": revisions(r["text"]),
                 "actions": actions(r["text"])} for r in case["rows"]]
        queries = []
        for q in case["queries"]:
            target = {"revisions": revisions(q["question"] + "\n" + q["claim"]),
                      "actions": actions(q["claim"], request=True)}
            terms = set(features(q["question"])) | set(features(q["claim"]))
            scores = [lexicon.score(lexicon.terms[offset + i], terms) for i in range(len(rows))]
            order = sorted(range(len(rows)), key=lambda i: -scores[i])
            positive = [i for i in order if scores[i] > 0]
            top_id = rows[positive[0]]["id"] if positive else None
            arms = {}
            for arm, gates in ARMS.items():
                checks = [check_scope(row, target, gates) for row in rows]
                audit = [{"row_id": rows[i]["id"], "bm25": scores[i], "reason": checks[i]}
                         for i in order]
                policies = {}
                for policy in POLICIES:
                    pool = positive[:1] if policy == "veto" else positive
                    winner = next((i for i in pool if checks[i] == "eligible"), None)
                    reason = "eligible" if winner is not None else "no_eligible_positive_candidate"
                    if not positive:
                        reason = "no_positive_lexical_candidate"
                    elif policy == "veto" and winner is None:
                        reason = checks[positive[0]]
                    policies[policy] = {"row_id": rows[winner]["id"] if winner is not None else None,
                                        "reason": reason, "top_lexical_id": top_id, "scores": audit}
                arms[arm] = policies
            queries.append({"id": q["id"], "target": target, "arms": arms})
        output.append({"case_id": case["case_id"], "rows": rows, "queries": queries})
        offset += len(rows)
    return {"cases": output}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, nargs="+")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = []
    for path in args.input:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            cases.extend(data["cases"] if "cases" in data else [data])
        else:
            cases.extend(data)
    result = json.dumps(evaluate(cases), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
