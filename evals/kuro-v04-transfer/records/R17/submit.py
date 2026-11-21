import json
from pathlib import Path
from tempfile import NamedTemporaryFile


STATES = ("NO_CHECK", "CHECK_FAILED", "NO_RECEIPT", "CONFLICT", "READY")
HOLD_REASONS = {
    "NO_CHECK": "採用版の点検記録なし",
    "CHECK_FAILED": "採用版の最新点検が失敗",
    "NO_RECEIPT": "予定の調整室に採用版の受領記録なし",
    "CONFLICT": "最新の受領記録と計画の照合符号が不一致",
}


def latest_by_version(records):
    latest = {}
    for record in records:
        key = (record["slot"], record["rev"])
        if key not in latest or record["seq"] > latest[key]["seq"]:
            latest[key] = record
    return latest


def state_for(plan, check, receipt):
    if check is None:
        return "NO_CHECK"
    if check["result"] == "fail":
        return "CHECK_FAILED"
    if receipt is None:
        return "NO_RECEIPT"
    if receipt["code"] != plan["code"]:
        return "CONFLICT"
    return "READY"


def summarize(data):
    checks = latest_by_version(data["checks"])
    failed_versions = {
        (row["slot"], row["rev"]) for row in data["checks"]
        if row["result"] == "fail"
    }
    receipts = latest_by_version(
        row for row in data["receipts"] if row["desk"] == data["desk"]
    )
    counts = dict.fromkeys(STATES, 0)
    queue = []
    recovered = []
    for plan in sorted(data["plan"], key=lambda row: row["slot"]):
        slot, rev = plan["slot"], plan["rev"]
        key = (slot, rev)
        check = checks.get(key)
        receipt = receipts.get(key)
        state = state_for(plan, check, receipt)
        counts[state] += 1
        queue.append({
            "slot": slot,
            "rev": rev,
            "state": state,
            "check_seq": check["seq"] if check is not None else None,
            "receipt_seq": receipt["seq"] if receipt is not None else None,
        })
        if key in failed_versions and check["result"] == "pass":
            recovered.append(slot)

    handoff = {
        "shift": data["shift"],
        "desk": data["desk"],
        "counts": counts,
        "recovered": recovered,
    }
    return queue, handoff


def write_json(path, value):
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                            delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def report(queue, handoff):
    held = [
        f'{row["slot"]}（{HOLD_REASONS[row["state"]]}）'
        for row in queue if row["state"] != "READY"
    ]
    ready = handoff["counts"]["READY"]
    print(f'勤務枠 {handoff["shift"]}、引渡先 {handoff["desk"]}。'
          f'全{len(queue)}件のうち{ready}件が使用可能です。')
    print("保留：" + ("、".join(held) if held else "なし") + "。")
    print("点検復旧：" + ("、".join(handoff["recovered"]) or "なし") + "。")


def main():
    with Path("/input/shift.json").open(encoding="utf-8") as source:
        queue, handoff = summarize(json.load(source))
    delivery = Path("/delivery")
    delivery.mkdir(parents=True, exist_ok=True)
    write_json(delivery / "queue.json", queue)
    write_json(delivery / "handoff.json", handoff)
    report(queue, handoff)


if __name__ == "__main__":
    main()
