import csv
import json
import sys
from pathlib import Path


EXPECTED = {
    "allocations.csv": (
        ["予約番号", "資料番号", "個体番号"],
        [
            ["R104", "T17", "C1702"],
            ["R108", "T17", "C1704"],
            ["R113", "T09", "C0902"],
            ["R121", "T23", "C2301"],
        ],
    ),
    "pickup.csv": (
        ["予約番号", "利用者番号", "受取館名", "受取期限"],
        [
            ["R108", "U51", "川辺分館", "2026-11-27"],
            ["R113", "U31", "中央図書館", "2026-11-27"],
            ["R121", "U23", "中央図書館", "2026-11-27"],
        ],
    ),
    "hold.csv": (
        ["予約番号", "受取館コード", "保留理由"],
        [["R104", "B07", "受取館未登録"]],
    ),
}


def inspect(directory):
    checks = {}
    for name, (header, rows) in EXPECTED.items():
        try:
            with (directory / "delivery" / name).open(
                encoding="utf-8-sig", newline=""
            ) as handle:
                actual = list(csv.reader(handle, strict=True))
        except (OSError, UnicodeError, csv.Error):
            actual = []
        checks[Path(name).stem] = actual == [header, *rows]
    return checks


if __name__ == "__main__":
    print(json.dumps(inspect(Path(sys.argv[1]))))
