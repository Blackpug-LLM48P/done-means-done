"""Check the three requested UTF-8 CSVs in an instance's delivery folder."""

import csv
import json
import sys
from pathlib import Path

SCHEDULE = [
    ["会場コード", "開始", "終了", "催しID", "催し名", "区分"],
    ["A", "10:00", "10:15", "P01", "入口で作品紹介", "一般"],
    ["A", "12:10", "12:30", "P05", "展示替え打合せ", "スタッフ"],
    ["A", "14:10", "14:45", "P06", "染め見本を読む", "一般"],
    ["B", "10:30", "11:00", "P02", "折りの実演", "一般"],
    ["B", "15:00", "15:50", "P08", "小冊子の交換会", "一般"],
    ["C", "10:30", "11:15", "P03", "製紙道具の話", "一般"],
    ["C", "13:30", "14:10", "P04", "紙と光の対話", "一般"],
]

PUBLIC = [
    ["開始", "終了", "会場名", "催し名"],
    ["10:00", "10:15", "中庭ギャラリー", "入口で作品紹介"],
    ["10:30", "11:00", "紙工房", "折りの実演"],
    ["10:30", "11:15", "閲覧室", "製紙道具の話"],
    ["13:30", "14:10", "閲覧室", "紙と光の対話"],
    ["14:10", "14:45", "中庭ギャラリー", "染め見本を読む"],
    ["15:00", "15:50", "紙工房", "小冊子の交換会"],
]

WITHDRAWALS = [
    ["催しID", "催し名", "取下理由"],
    ["P07", "紙の音を聴く", "機材調整のため"],
]

REQUIREMENTS = [
    ("スタッフ枠を含む確定会場別進行表", "schedule.csv", SCHEDULE),
    ("来場者向け時刻表", "public.csv", PUBLIC),
    ("予告チラシ取下げ一覧", "withdrawals.csv", WITHDRAWALS),
]


def matches_file(path, expected):
    try:
        with path.open(encoding="utf-8-sig", newline="") as source:
            return list(csv.reader(source, strict=True)) == expected
    except (OSError, UnicodeError, csv.Error):
        return False


def main():
    delivery = Path(sys.argv[1]) / "delivery" if len(sys.argv) == 2 else None
    result = {
        name: delivery is not None and matches_file(delivery / filename, expected)
        for name, filename, expected in REQUIREMENTS
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
