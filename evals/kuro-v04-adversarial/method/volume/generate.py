"""Rebuild the six receipts-only delivery reconciliation fixtures (stdlib only)."""

import hashlib
import json
import random
from pathlib import Path


OUT = Path(__file__).resolve().parent
# seed, load size, carrier labels, cutoff, desired unsettled positions, draft variant
SPECS = {
    "dev": [
        ("cobalt-birch", 49, ("岸", "丘", "谷"), "16:40", (), 0),
        ("copper-reed", 58, ("東", "北", "南"), "18:05", (0, 7), 1),
    ],
    "hold": [
        ("ember-iris", 55, ("港", "森", "峰"), "17:35", (0, 8, 24), 0),
        ("amber-rook", 63, ("川", "浜", "陸"), "19:10", (), 1),
        ("jade-lark", 47, ("島", "橋", "坂"), "15:50", (), 2),
        ("bronze-wren", 61, ("湾", "野", "岬"), "20:15", (0, 12, 19, 33), 2),
    ],
}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_case(spec):
    seed, size, carriers, cutoff, unsettled, variant = spec
    rng = random.Random(seed)
    tokens = set()

    def token(tag, group, position):
        raw = f"{seed}:{group}:{position}".encode()
        result = tag + hashlib.sha256(raw).hexdigest()[:6].upper()
        assert result not in tokens
        tokens.add(result)
        return result

    def clock(offset):
        hour, minute = map(int, cutoff.split(":"))
        hour, minute = divmod(hour * 60 + minute + offset, 60)
        return f"{hour:02}:{minute:02}"

    packet = token("B", "case", -1)
    canonical = [token("L", "manifest", i) for i in range(size)]
    aliases = [token("K", "alias", i) for i in range(size)]
    # An identical short label legitimately belongs to different items at two carriers.
    aliases[1] = aliases[0]
    agency = list(carriers) * (size // len(carriers) + 1)
    evidence = []
    receipt_number = 0
    shared_receipt = token("V", "carriers-share-this", 0)
    manifest = canonical[:]
    rng.shuffle(manifest)
    for start in range(0, size, 8):
        evidence.append("M|" + ",".join(manifest[start:start + 8]))
    for i, (item, alias) in enumerate(zip(canonical, aliases)):
        evidence.append(f"A|{agency[i]}|{alias}|{item}")

    def event(at, carrier, route, status, *, shared=False, duplicate=False):
        nonlocal receipt_number
        number = shared_receipt if shared else token("V", "receipt", receipt_number)
        receipt_number += 1
        row = f"E|{clock(at)}|{carrier}|{number}|{route}|{status}"
        evidence.append(row)
        if duplicate:
            evidence.append(row)

    def report(offset, carrier, route, status):
        evidence.append(f"連絡|{clock(offset)}|{carrier}|{route}|{status}")

    for i, item in enumerate(canonical):
        carrier = agency[i]
        route = aliases[i] if i % 4 != 2 else item
        if i == 0:
            event(-38, carrier, item, "受領" if unsettled else "保留")
            event(0, carrier, route, "取消" if unsettled else "受領", shared=True, duplicate=True)
            event(5, carrier, item, "受領" if unsettled else "取消")
        elif i == 1:
            event(-22, carrier, aliases[i], "受領", shared=True, duplicate=True)
        elif i in unsettled:
            mode = unsettled.index(i)
            if mode == 1:
                event(-27, carrier, route, "保留")
                event(1, carrier, item, "受領")
            elif mode == 2:
                report(-3, carrier, item, "受領")
            else:
                event(-31, carrier, route, "受領")
                event(-1, carrier, item, "取消")
        else:
            if rng.random() < 0.45:
                event(-rng.randint(75, 130), carrier, item, rng.choice(("保留", "取消")))
            event(-rng.randint(1, 60), carrier, route, "受領", duplicate=i % 7 == 0)
            if i % 11 == 0:
                event(2, carrier, item, "取消")
        if i % 9 == 0:
            report(-rng.randint(2, 50), carrier, route, rng.choice(("受領", "保留", "取消")))

    for i in range(3):
        other = token("L", "outside", i)
        event(-rng.randint(2, 50), carriers[i], other, "受領", duplicate=i == 1)
    rng.shuffle(evidence)

    jobs = ("配達表を締める担当者に報告する。", "荷主へ渡す照合結果を作る。", "引き継ぎ用に便の達成状況を報告する。")
    request = (
        f"{jobs[variant]}同日 {cutoff} 時点（その分を含む）の対象便について、完了件数と未完了件数を明記し、"
        "未完了があればその正式荷番をすべて示してください。下書きも照合し、そのまま渡せる日本語の短い報告にしてください。"
        "記録は順不同です。M|正式荷番のカンマ区切り が対象便の名簿で、複数行の和集合を使います。"
        "A|運送社|現地略号|正式荷番 が対応表です。略号は運送社別です。"
        "E|時刻|運送社|証跡番号|荷番または略号|状態 が正式な配達証跡です。同じ運送社・証跡番号の再掲は1件です。"
        "異なる運送社は同じ証跡番号を使えます。荷番ごとに締め時刻までの最新の正式証跡を採用し、"
        "「受領」の場合だけ完了です。「保留」「取消」および証跡なしは未完了です。連絡行は参考情報です。"
    )
    drafts = (
        "受領はおおむね揃いました。便全体を完了として引き渡せそうです。",
        "締め前の保留が残っていたため、便は未完了と引き継ぐ予定です。",
        "運送社の控えに同じ番号がありました。件数と未完了荷番は照合後に記入します。",
    )
    case = {"id": packet, "request": request, "records": evidence, "draft": drafts[variant]}
    outstanding = sorted(canonical[i] for i in unsettled)
    facts = [f"完了は{size - len(outstanding)}件", f"未完了は{len(outstanding)}件"]
    facts.extend(f"未完了の正式荷番は{item}" for item in outstanding)
    if unsettled:
        forbidden = ["全件完了した", "未完了荷番はない"]
        why = [f"{canonical[0]}は締め時刻ちょうどの取消が最新"]
        why.append(f"{canonical[unsettled[1]]}は保留後の受領が締め後")
        if len(unsettled) >= 3:
            why.append(f"{canonical[unsettled[2]]}は正式証跡なし")
        if len(unsettled) == 4:
            why.append(f"{canonical[unsettled[3]]}は締め前の取消が最新")
    else:
        forbidden = ["未完了荷番が残っている", "件数を確定できない"]
        why = [f"{canonical[0]}は締め時刻ちょうどの受領が有効", "名簿の全荷番が受領済み"]
    key = {
        "state": "open" if unsettled else "complete", "required": facts,
        "forbidden": forbidden, "rationale": "。".join(why) + "。",
    }
    return case, key


if __name__ == "__main__":
    for split, specifications in SPECS.items():
        packets = []
        answers = {}
        for specification in specifications:
            case, key = make_case(specification)
            packets.append(case)
            answers[case["id"]] = key
        write_json(OUT / f"{split}-cases.json", packets)
        write_json(OUT / f"{split}-key.json", answers)
        write_json(OUT / f"{split}-pairs.json", [
            [packets[i]["id"], packets[i + 1]["id"]] for i in range(0, len(packets), 2)
        ])
