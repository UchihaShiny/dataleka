"""Tạo 4 dataset của kho: raw, silver, gold, pii. Chạy lại nhiều lần không lỗi, không xoá gì.

Chạy từ thư mục gốc:  python -m pipelines.setup_datasets
"""

import sys

from pipelines.bq import client

sys.stdout.reconfigure(encoding="utf-8")

DATASETS = {
    "raw": "Bronze: dữ liệu thô từ Shopify, Meta, Klaviyo, nạp bằng dlt. Không sửa tay.",
    "silver": "Silver: dbt staging/intermediate, đã đổi kiểu, ngày theo America/Phoenix.",
    "gold": "Gold: dbt marts, star schema và chỉ số chung. MCP đọc từ đây.",
    "pii": "PII: email, tên, địa chỉ, SĐT. Silver/gold chỉ nối qua customer_key. MCP không được đọc.",
}

from google.cloud import bigquery  # noqa: E402

bq = client()
for name, description in DATASETS.items():
    dataset = bigquery.Dataset(f"{bq.project}.{name}")
    dataset.location = bq.location
    dataset.description = description
    created = bq.create_dataset(dataset, exists_ok=True)
    expiry = created.default_table_expiration_ms
    print(f"  {created.dataset_id}: {created.location}, bảng hết hạn sau "
          f"{expiry // 86_400_000 if expiry else 'không'} ngày")

found = sorted(d.dataset_id for d in bq.list_datasets())
missing = sorted(set(DATASETS) - set(found))
if missing:
    sys.exit(f"Thiếu dataset: {', '.join(missing)}")
print(f"OK: {', '.join(found)}")
