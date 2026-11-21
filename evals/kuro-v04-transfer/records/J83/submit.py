import json
import os
import tempfile
from pathlib import Path


REASONS = {
    "NO_CHECK": "採用版の点検記録なし",
    "CHECK_FAILED": "採用版の最新点検が失敗",
    "NO_RECEIPT": "予定の調整室から採用版の受領記録なし",
    "CONFLICT": "最新の受領記録の照合符号が計画と不一致",
}


def latest_by_version(records):
    latest = {}
    for record in records:
        key = (record["slot"], record["rev"])
        if key not in latest or record["seq"] > latest[key]["seq"]:
            latest[key] = record
    return latest


def classify(item, check, receipt):
    if check is None:
        return "NO_CHECK"
    if check["result"] == "fail":
        return "CHECK_FAILED"
    if receipt is None:
        return "NO_RECEIPT"
    if receipt["code"] != item["code"]:
        return "CONFLICT"
    return "READY"


def prepare(shift):
    checks = latest_by_version(shift["checks"])
    failures = {
        (check["slot"], check["rev"])
        for check in shift["checks"] if check["result"] == "fail"
    }
    receipts = latest_by_version(
        receipt for receipt in shift["receipts"] if receipt["desk"] == shift["desk"]
    )
    counts = dict.fromkeys([*REASONS, "READY"], 0)
    recovered = []
    queue = []
    for item in sorted(shift["plan"], key=lambda entry: entry["slot"]):
        slot, rev = key = (item["slot"], item["rev"])
        check, receipt = checks.get(key), receipts.get(key)
        state = classify(item, check, receipt)
        if check is not None and check["result"] == "pass" and key in failures:
            recovered.append(slot)
        counts[state] += 1
        queue.append({
            "slot": slot,
            "rev": rev,
            "state": state,
            "check_seq": check["seq"] if check is not None else None,
            "receipt_seq": receipt["seq"] if receipt is not None else None,
        })
    return queue, {
        "shift": shift["shift"],
        "desk": shift["desk"],
        "counts": counts,
        "recovered": recovered,
    }


def save_json(path, value):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
        temp = Path(output.name)
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def main():
    shift = json.loads(Path("/input/shift.json").read_text(encoding="utf-8"))
    queue, handoff = prepare(shift)
    delivery = Path("/delivery")
    delivery.mkdir(parents=True, exist_ok=True)
    save_json(delivery / "queue.json", queue)
    save_json(delivery / "handoff.json", handoff)

    held = [f'{row["slot"]}（{REASONS[row["state"]]}）' for row in queue
            if row["state"] != "READY"]
    print(f'勤務枠 {handoff["shift"]}、予定の引渡先 {handoff["desk"]}。'
          f'全{len(queue)}番組のうち{handoff["counts"]["READY"]}件が使用可能です。')
    print("保留：" + ("、".join(held) if held else "なし") + "。")
    print("点検復旧：" + ("、".join(handoff["recovered"]) or "なし") + "。")


if __name__ == "__main__":
    main()
