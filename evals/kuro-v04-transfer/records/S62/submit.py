import json
from pathlib import Path


REASONS = {
    "NO_CHECK": "採用版の点検記録なし",
    "CHECK_FAILED": "採用版の最新点検が失敗",
    "NO_RECEIPT": "予定の調整室に採用版の受領記録なし",
    "CONFLICT": "最新受領記録の照合符号が計画と不一致",
}


def latest_by_version(records):
    latest = {}
    for record in records:
        key = (record["slot"], record["rev"])
        if key not in latest or record["seq"] > latest[key]["seq"]:
            latest[key] = record
    return latest


def classify(plan, check, receipt):
    if check is None:
        return "NO_CHECK"
    if check["result"] == "fail":
        return "CHECK_FAILED"
    if receipt is None:
        return "NO_RECEIPT"
    if receipt["code"] != plan["code"]:
        return "CONFLICT"
    return "READY"


def build_handoff(data):
    checks = latest_by_version(data["checks"])
    receipts = latest_by_version(
        record for record in data["receipts"] if record["desk"] == data["desk"]
    )
    failures = {
        (record["slot"], record["rev"])
        for record in data["checks"]
        if record["result"] == "fail"
    }
    recovered = []
    queue = []
    counts = dict.fromkeys([*REASONS, "READY"], 0)
    for plan in sorted(data["plan"], key=lambda item: item["slot"]):
        key = (plan["slot"], plan["rev"])
        check = checks.get(key)
        receipt = receipts.get(key)
        state = classify(plan, check, receipt)
        counts[state] += 1
        if key in failures and check["result"] == "pass":
            recovered.append(plan["slot"])
        queue.append({
            "slot": plan["slot"],
            "rev": plan["rev"],
            "state": state,
            "check_seq": check["seq"] if check is not None else None,
            "receipt_seq": receipt["seq"] if receipt is not None else None,
        })
    return queue, {
        "shift": data["shift"],
        "desk": data["desk"],
        "counts": counts,
        "recovered": recovered,
    }


def main():
    data = json.loads(Path("/input/shift.json").read_text(encoding="utf-8"))
    queue, handoff = build_handoff(data)
    delivery = Path("/delivery")
    delivery.mkdir(parents=True, exist_ok=True)
    for name, payload in [("queue.json", queue), ("handoff.json", handoff)]:
        (delivery / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    held = [
        f'{item["slot"]}（{REASONS[item["state"]]}）'
        for item in queue if item["state"] != "READY"
    ]
    print(f'勤務枠 {handoff["shift"]}、引渡先 {handoff["desk"]}。'
          f'全{len(queue)}番組のうち{handoff["counts"]["READY"]}件が使用可能です。')
    print("保留：" + ("、".join(held) or "なし") + "。")
    print("点検復旧：" + ("、".join(handoff["recovered"]) or "なし") + "。")


if __name__ == "__main__":
    main()
