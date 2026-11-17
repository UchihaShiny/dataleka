"""Nạp Shopify vào BigQuery: raw.shopify_orders, _order_line_items, _order_refunds, _products,
_product_variants và pii.shopify_customers. Ghi đè cả bảng, chạy lại không trùng. Dùng token Shopify.

Mặc định incremental: chỉ kéo đơn có updated_at từ mốc mới nhất trong BigQuery trừ 1 ngày, gộp vào
bản hiện có. Lần đầu (chưa có bảng) hoặc --full thì kéo full từ 2024-11-01.
File tạm trên máy (có PII) bị xoá sau mỗi lần chạy, kể cả khi lỗi.

Chạy từ thư mục gốc:  python -m pipelines.load_shopify [--full]
"""

import argparse
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

from pipelines import common, dates
from pipelines.bq import ROOT, client
from pipelines.sources.shopify import shopify

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv(ROOT / ".env")

TABLES = {"orders": "raw.shopify_orders", "items": "raw.shopify_order_line_items",
          "refunds": "raw.shopify_order_refunds", "customers": "pii.shopify_customers"}


def read_base(bq) -> dict | None:
    """Đọc bản hiện có bằng list_rows: miễn phí, không tính vào quota truy vấn. Thiếu bảng thì None."""
    from google.api_core.exceptions import NotFound

    base = {}
    for name, table in TABLES.items():
        try:
            base[name] = [dict(row) for row in bq.list_rows(f"{bq.project}.{table}")]
        except NotFound:
            return None
    return base


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--full", action="store_true", help="kéo lại full lịch sử, ví dụ mỗi tuần một lần")
    args = parser.parse_args()

    started = datetime.now(timezone.utc)   # trước khi kéo: đơn tạo trước lúc này đều có trong lần kéo
    bq = client()
    base = None if args.full else read_base(bq)
    if base:
        print(f"Bản hiện có: {len(base['orders']):,} đơn, {len(base['items']):,} line item")
    try:
        loaded = common.run(shopify(base), "shopify", "shopify", bq=bq)
    finally:
        common.reset("shopify")  # xoá JSONL có PII trên máy
    done = dates.record_load("shopify", started)
    print(f"Ngày đã trọn theo lúc nạp (giờ Phoenix): {done}")
    print("OK: " + ", ".join(f"{name} {rows:,}" for name, rows in loaded.items()))
