import json
from pathlib import Path


HOLD_REASONS = {
    "NO_CHECK": "採用版の点検記録なし",
    "CHECK_FAILED": "採用版の最新点検が失敗",
    "NO_RECEIPT": "予定の調整室から採用版の受領記録なし",
    "CONFLICT": "最新受領記録の照合符号が計画と不一致",
}


def index_latest(records):
    latest = {}
    for record in records:
        key = (record["slot"], record["rev"])
        if key not in latest or record["seq"] > latest[key]["seq"]:
            latest[key] = record
    return latest


def assemble(data):
    checks = index_latest(data["checks"])
    failures = {
        (check["slot"], check["rev"])
        for check in data["checks"] if check["result"] == "fail"
    }
    receipts = index_latest(
        receipt for receipt in data["receipts"] if receipt["desk"] == data["desk"]
    )
    counts = dict.fromkeys((*HOLD_REASONS, "READY"), 0)
    queue = []
    recovered = []
    for plan in sorted(data["plan"], key=lambda row: row["slot"]):
        key = (plan["slot"], plan["rev"])
        check = checks.get(key)
        receipt = receipts.get(key)
        if check is None:
            state = "NO_CHECK"
        elif check["result"] == "fail":
            state = "CHECK_FAILED"
        else:
            if key in failures:
                recovered.append(plan["slot"])
            if receipt is None:
                state = "NO_RECEIPT"
            elif receipt["code"] != plan["code"]:
                state = "CONFLICT"
            else:
                state = "READY"
        counts[state] += 1
        queue.append({
            "slot": plan["slot"],
            "rev": plan["rev"],
            "state": state,
            "check_seq": check["seq"] if check is not None else None,
            "receipt_seq": receipt["seq"] if receipt is not None else None,
        })
    handoff = {
        "shift": data["shift"], "desk": data["desk"],
        "counts": counts, "recovered": recovered,
    }
    return queue, handoff


def report(queue, handoff):
    held = [
        f'{entry["slot"]}（{HOLD_REASONS[entry["state"]]}）'
        for entry in queue if entry["state"] in HOLD_REASONS
    ]
    print(f'勤務枠 {handoff["shift"]}、予定の引渡先 {handoff["desk"]}。'
          f'全{len(queue)}件中{handoff["counts"]["READY"]}件が使用可能です。')
    print("保留：" + ("、".join(held) or "なし") + "。")
    print("点検復旧：" + ("、".join(handoff["recovered"]) or "なし") + "。")


def main():
    data = json.loads(Path("/input/shift.json").read_text(encoding="utf-8"))
    queue, handoff = assemble(data)
    delivery = Path("/delivery")
    delivery.mkdir(exist_ok=True, parents=True)
    for name, value in (("queue.json", queue), ("handoff.json", handoff)):
        (delivery / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    report(queue, handoff)


if __name__ == "__main__":
    main()
