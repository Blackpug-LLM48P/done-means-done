import json
from pathlib import Path
from tempfile import NamedTemporaryFile


REASONS = {
    "NO_CHECK": "採用版の点検記録なし",
    "CHECK_FAILED": "採用版の最新点検で失敗",
    "NO_RECEIPT": "予定の調整室から採用版の受領記録なし",
    "CONFLICT": "最新の受領記録と計画の照合符号が不一致",
}


def latest_by_slot(records):
    latest = {}
    for record in records:
        slot = record["slot"]
        if slot not in latest or record["seq"] > latest[slot]["seq"]:
            latest[slot] = record
    return latest


def classify(check, receipt, code):
    if check is None:
        return "NO_CHECK"
    if check["result"] == "fail":
        return "CHECK_FAILED"
    if receipt is None:
        return "NO_RECEIPT"
    if receipt["code"] != code:
        return "CONFLICT"
    return "READY"


def summarize(data):
    plan = {item["slot"]: item for item in data["plan"]}
    versions = {(slot, item["rev"]) for slot, item in plan.items()}
    checks = [
        row for row in data["checks"] if (row["slot"], row["rev"]) in versions
    ]
    latest_checks = latest_by_slot(checks)
    latest_receipts = latest_by_slot(
        row for row in data["receipts"]
        if (row["slot"], row["rev"]) in versions and row["desk"] == data["desk"]
    )
    failed_slots = {row["slot"] for row in checks if row["result"] == "fail"}
    counts = dict.fromkeys([*REASONS, "READY"], 0)
    queue = []
    recovered = []
    for slot in sorted(plan):
        item = plan[slot]
        check = latest_checks.get(slot)
        receipt = latest_receipts.get(slot)
        state = classify(check, receipt, item["code"])
        queue.append({
            "slot": slot,
            "rev": item["rev"],
            "state": state,
            "check_seq": check["seq"] if check is not None else None,
            "receipt_seq": receipt["seq"] if receipt is not None else None,
        })
        counts[state] += 1
        if slot in failed_slots and check["result"] == "pass":
            recovered.append(slot)
    handoff = {
        "shift": data["shift"],
        "desk": data["desk"],
        "counts": counts,
        "recovered": recovered,
    }
    return queue, handoff


def save_json(path, value):
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                            delete=False) as stream:
        temp = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def report(queue, handoff):
    held = [
        f'{row["slot"]}（{REASONS[row["state"]]}）'
        for row in queue if row["state"] != "READY"
    ]
    print(f'勤務枠 {handoff["shift"]}、引渡先 {handoff["desk"]}。'
          f'全{len(queue)}件のうち{handoff["counts"]["READY"]}件が使用可能です。')
    print("保留：" + ("、".join(held) if held else "なし"))
    print("点検復旧：" + ("、".join(handoff["recovered"]) or "なし"))


def main():
    with Path("/input/shift.json").open(encoding="utf-8") as stream:
        queue, handoff = summarize(json.load(stream))
    delivery = Path("/delivery")
    delivery.mkdir(exist_ok=True)
    save_json(delivery / "queue.json", queue)
    save_json(delivery / "handoff.json", handoff)
    report(queue, handoff)


if __name__ == "__main__":
    main()
