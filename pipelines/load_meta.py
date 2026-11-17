"""Nạp Meta Ads vào BigQuery: raw.meta_ad_insights_daily (ad × ngày) và raw.meta_ads (cây ad).

Chỉ gọi Meta cho khoảng ngày cần lấy, ghép với cache trên máy, rồi ghi đè cả bảng.
Dùng token Meta. Tự từ chối chạy trong giờ làm việc Phoenix (22:00–07:00 giờ Việt Nam) vì quota dùng chung với
đội ads; mỗi lần tối đa 31 ngày.

Chạy từ thư mục gốc:
  python -m pipelines.load_meta                     7 ngày đã trọn gần nhất (chạy hằng ngày)
  python -m pipelines.load_meta --since 2026-10-01 --until 2026-10-31   nạp dần từng tháng
  python -m pipelines.load_meta --since 2026-10-01 --until 2026-10-31
"""

import argparse
import sys
from datetime import date

from dotenv import load_dotenv

from pipelines import common
from pipelines.bq import ROOT
from pipelines.dates import PHOENIX, guard_work_hours, last_complete_day, window  # noqa: F401
from pipelines.sources.meta import meta

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv(ROOT / ".env")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", type=date.fromisoformat)
    parser.add_argument("--until", type=date.fromisoformat)
    parser.add_argument("--force", action="store_true", help="chạy cả trong giờ làm việc Phoenix (đã báo anh)")
    args = parser.parse_args()

    guard_work_hours(args.force)

    since, until = window(args, last_complete_day())
    loaded = common.run(meta(since, until), "meta", "meta")
    print("OK: " + ", ".join(f"{name} {rows:,}" for name, rows in loaded.items()))
