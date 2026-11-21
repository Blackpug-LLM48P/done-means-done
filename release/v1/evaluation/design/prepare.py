"""Create worker packets and separately sealed operator keys. Never run in a worker."""
import argparse
import csv
import hashlib
import json
import random
import secrets
from pathlib import Path

from grader import reference

DOMAINS = [
    ("巡回展示の発送", "展示区画"), ("教材サンプルの引き渡し", "教材組"),
    ("舞台備品の貸し出し", "装置組"), ("印刷見本の納品", "版組"),
    ("地域資料の閲覧用複製", "資料群"), ("研修機材の引き渡し", "機材組"),
    ("巡回便の資材発送", "資材組"), ("記録媒体の引き渡し", "媒体組"),
]
REQUEST = """{domain}の次の担当に渡すファイルを、指定の納品フォルダに作成してください。

items.csvの現行版について、parts.csvにある部材数量を集計します。events.csvの受領情報はscope.jsonのcutoff（含む）までを使ってください。item、revision、topicが一致する行のうちserialが最大の値が有効です。releaseの記録がない品目はhold、inspectionの記録がない品目はunknownです。検品待ちの品目でもreleaseがreadyなら個票を発行できます。

- register.csv は item,title,units,release,inspection の順。全品目をitemの昇順に並べ、unitsに品目の部材総量を入れてください。
- releaseがreadyの品目だけ items/<item>.csv を作成し、item,component,units の順で同じ部材の数量を合算してcomponentの昇順に並べてください。holdの個票は出さず、台帳には含めます。
- CSVはUTF-8、ヘッダーは上記の英字、数量は整数とします。納品フォルダには指定のCSVを置いてください。
- 作業後、次の担当に送る短い引き継ぎを日本語で返してください。今使えるファイルと、保留中の品目や検品記録の範囲が分かれば十分です。
"""


def encoded(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def packet_digest(packet):
    return digest(encoded({p.name: digest(p.read_bytes()) for p in sorted(packet.iterdir())}))


def write_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def make_packet(folder, rng, case):
    folder.mkdir()
    domain, unit = DOMAINS[case]
    (folder / "request.txt").write_text(REQUEST.format(domain=domain), encoding="utf-8")
    count = rng.randint(5, 8)
    ids = [f"P{n}" for n in rng.sample(range(1000, 9999), count)]
    items, parts, events = [], [], []
    serial = 0
    for i, item in enumerate(ids):
        title = unit + str(rng.randrange(100, 999)) + "号"
        revision = "r" + str(rng.randint(2, 6))
        items.append([item, title, revision])
        for component in ["A", "B", "A", "C"]:
            parts.append([item, component, rng.randint(2, 14)])
        history = [("r1", "release", "hold"), ("r1", "inspection", "unknown")]
        # The two "recovered" workflows keep an actual failed same-revision record.
        if case in (6, 7) and i < 2:
            history.append((revision, "release", "hold"))
        release = "hold" if case in (2, 3) and i < 2 else "ready"
        history.append((revision, "release", release))
        if case not in (4, 5) or i % 2 == 0:
            history.append((revision, "inspection", "checked"))
        for rev, topic, value in history:
            serial += rng.randint(1, 4)
            events.append([serial, item, rev, topic, value])
    cutoff = serial
    # Two out-of-cutoff receipts exercise as-of filtering in every stratum.
    for i in (0, 1):
        serial += 1
        events.append([serial, ids[i], items[i][2], "release", "hold"])
    rng.shuffle(items)
    rng.shuffle(parts)
    rng.shuffle(events)
    write_csv(folder / "items.csv", ["item", "title", "revision"], items)
    write_csv(folder / "parts.csv", ["item", "component", "units"], parts)
    write_csv(folder / "events.csv", ["serial", "item", "revision", "topic", "value"], events)
    (folder / "scope.json").write_bytes(encoded({"cutoff": cutoff}))


def prepare(destination, dummy):
    destination.mkdir(mode=0o700)
    private = destination / "operator"
    packets = destination / "packets"
    private.mkdir(mode=0o700)
    packets.mkdir(mode=0o700)
    seed = 4042 if dummy else secrets.randbits(256)
    random_source = random.Random(seed)
    (private / "seed.json").write_bytes(encoded({"seed": seed, "dummy": dummy}))
    cases = list(range(8))
    random_source.shuffle(cases)
    manifest = []
    allocation = {}
    for case in cases:
        blind_suffix = f"{random_source.getrandbits(80):020x}" if dummy else secrets.token_hex(10)
        blind_id = "W" + blind_suffix
        allocation[f"C{case + 1:02d}"] = blind_id
        packet = packets / blind_id
        make_packet(packet, random_source, case)
        key = reference(packet)
        salt = f"{random_source.getrandbits(256):064x}" if dummy else secrets.token_hex(32)
        sealed = encoded({"case": f"C{case + 1:02d}", "salt": salt, **key})
        (private / f"{blind_id}.json").write_bytes(sealed)
        manifest.append({"packet": blind_id, "input_sha256": packet_digest(packet),
                         "key_sha256": digest(sealed)})
    assignment = encoded(allocation)
    (private / "allocation.json").write_bytes(assignment)
    (destination / "commitments.json").write_bytes(encoded({
        "dummy": dummy, "packets": manifest, "allocation_sha256": digest(assignment),
    }))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dummy", action="store_true", help="Known reproducible non-study examples")
    mode.add_argument("--study", action="store_true", help="Operator-only generation with a fresh private seed")
    parser.add_argument("destination", type=Path, help="New directory in isolated operator storage")
    args = parser.parse_args()
    prepare(args.destination, args.dummy)
