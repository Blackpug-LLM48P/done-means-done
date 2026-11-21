import json
from pathlib import Path
from tempfile import NamedTemporaryFile


REASONS = {
    "NO_CHECK": "採用版の点検記録なし",
    "CHECK_FAILED": "採用版の最新点検が失敗",
    "NO_RECEIPT": "予定の調整室から採用版の受領記録なし",
    "CONFLICT": "最新受領記録の照合符号が計画と不一致",
}


def latest_by_version(records):
    latest = {}
    for record in records:
        key = (record["slot"], record["rev"])
        if key not in latest or record["seq"] > latest[key]["seq"]:
            latest[key] = record
    return latest


def state_for(check, receipt, code):
    if check is None:
        return "NO_CHECK"
    if check["result"] == "fail":
        return "CHECK_FAILED"
    if receipt is None:
        return "NO_RECEIPT"
    if receipt["code"] != code:
        return "CONFLICT"
    return "READY"


def summarize(shift):
    checks = latest_by_version(shift["checks"])
    receipts = latest_by_version(
        record for record in shift["receipts"] if record["desk"] == shift["desk"]
    )
    failed_versions = {
        (record["slot"], record["rev"])
        for record in shift["checks"]
        if record["result"] == "fail"
    }
    counts = dict.fromkeys((*REASONS, "READY"), 0)
    queue = []
    recovered = []
    for item in sorted(shift["plan"], key=lambda item: item["slot"]):
        slot, rev = item["slot"], item["rev"]
        key = (slot, rev)
        check, receipt = checks.get(key), receipts.get(key)
        state = state_for(check, receipt, item["code"])
        counts[state] += 1
        if key in failed_versions and check["result"] == "pass":
            recovered.append(slot)
        queue.append({
            "slot": slot,
            "rev": rev,
            "state": state,
            "check_seq": check["seq"] if check is not None else None,
            "receipt_seq": receipt["seq"] if receipt is not None else None,
        })
    return queue, {
        "shift": shift["shift"], "desk": shift["desk"],
        "counts": counts, "recovered": recovered,
    }


def write_json(path, data):
    with NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8",
                            delete=False) as stream:
        temporary = Path(stream.name)
    try:
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    shift = json.loads(Path("/input/shift.json").read_text(encoding="utf-8"))
    queue, handoff = summarize(shift)
    delivery = Path("/delivery")
    delivery.mkdir(parents=True, exist_ok=True)
    write_json(delivery / "queue.json", queue)
    write_json(delivery / "handoff.json", handoff)
    held = [
        f"{entry['slot']}（{REASONS[entry['state']]}）"
        for entry in queue if entry["state"] != "READY"
    ]
    print(f"勤務枠 {handoff['shift']}、引渡先 {handoff['desk']}。"
          f"全{len(queue)}件中{handoff['counts']['READY']}件が使用可能です。")
    print("保留：" + ("、".join(held) or "なし"))
    print("点検復旧：" + ("、".join(handoff["recovered"]) or "なし"))


if __name__ == "__main__":
    main()
