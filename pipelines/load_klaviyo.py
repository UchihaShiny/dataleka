"""Nạp Klaviyo vào BigQuery: raw.klaviyo_campaigns, _campaign_messages, _flows, _metrics, _message_daily.

Chỉ đọc (private key read-only). Ghi đè cả bảng, chạy lại không trùng.
Chạy từ thư mục gốc:
  python -m pipelines.load_klaviyo                                        7 ngày đã trọn gần nhất
  python -m pipelines.load_klaviyo --since 2026-10-01 --until 2026-10-31  nạp dần từng tháng
"""

import argparse
import sys
from datetime import date

from dotenv import load_dotenv

from pipelines import common
from pipelines.bq import ROOT
from pipelines.dates import guard_work_hours, last_complete_day, window
from pipelines.sources.klaviyo import klaviyo

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
    loaded = common.run(klaviyo(since, until), "klaviyo", "klaviyo")
    print("OK: " + ", ".join(f"{name} {rows:,}" for name, rows in loaded.items()))
