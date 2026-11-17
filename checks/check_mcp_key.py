"""Kiểm khoá MCP (MCP_CREDENTIALS trong .env) đúng là CHỈ ĐỌC silver + gold, như brief tuần 4 yêu cầu.

Đạt khi: đọc được gold và silver; KHÔNG đọc được raw, pii; KHÔNG tạo được bảng trong gold. Nếu tạo bảng lại thành
công (khoá còn quyền ghi) thì script xoá ngay bảng thử đó rồi báo LỖI.
Silver phần lớn là view đọc từ raw: khoá đọc được view silver nhờ silver là AUTHORIZED DATASET của raw
(docs/cai-dat-bigquery.md mục 9), còn đọc thẳng raw vẫn bị chặn.

Chạy từ thư mục gốc (dùng khoá MCP):  python checks/check_mcp_key.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from google.api_core import exceptions  # noqa: E402
from google.cloud import bigquery  # noqa: E402

from pipelines.bq import MCP_KEY_ENV, client  # noqa: E402

if not os.environ.get(MCP_KEY_ENV, "").strip():
    sys.exit(f"Chưa có {MCP_KEY_ENV} trong .env. Làm theo docs/cai-dat-bigquery.md mục 8 trước.")

bq = client(MCP_KEY_ENV)
print(f"Khoá MCP: {bq._credentials.service_account_email}")
if "pipeline" in bq._credentials.service_account_email:
    sys.exit("LỖI: MCP_CREDENTIALS đang trỏ vào khoá pipeline (có quyền ghi). Phải là khoá datae-mcp.")
failed = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global failed
    failed += not ok
    print(f"  {'✓' if ok else '✗'} {label}{(': ' + detail) if detail else ''}")


def can_read(sql: str) -> tuple[bool, str]:
    try:
        list(bq.query(sql, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=50 * 1024 * 1024)).result())
        return True, ""
    except exceptions.Forbidden:
        return False, "bị chặn (403)"
    except exceptions.NotFound as error:
        return False, f"không thấy bảng: {str(error)[:120]}"


ok, detail = can_read(f"select date from `{bq.project}.gold.daily_performance` limit 1")
check("đọc được gold.daily_performance", ok, detail)
ok, detail = can_read(f"select date from `{bq.project}.gold.forecast_daily` limit 1")
check("đọc được gold.forecast_daily (bảng do forecast.publish ghi)", ok, detail)
ok, detail = can_read(f"select order_id from `{bq.project}.silver.stg_orders` limit 1")
check("đọc được silver.stg_orders (view đọc raw, cần authorized dataset)", ok, detail)
ok, detail = can_read(f"select sku_prefix from `{bq.project}.silver.product_lines` limit 1")
check("đọc được silver.product_lines (bảng seed)", ok, detail)
for table in ["raw.shopify_orders", "pii.shopify_customers"]:
    ok, detail = can_read(f"select 1 from `{bq.project}.{table}` limit 1")
    check(f"KHÔNG đọc được {table}", not ok and "403" in detail, detail or "ĐỌC ĐƯỢC, khoá có quyền quá rộng")

test_id = f"{bq.project}.gold._mcp_write_test"
try:
    bq.create_table(bigquery.Table(test_id, schema=[bigquery.SchemaField("x", "INT64")]))
except exceptions.Forbidden:
    check("KHÔNG tạo được bảng trong gold", True, "bị chặn (403)")
else:
    bq.delete_table(test_id, not_found_ok=True)
    check("KHÔNG tạo được bảng trong gold", False, "TẠO ĐƯỢC (đã xoá bảng thử): khoá còn quyền ghi")

print(f"\n{'Đạt: khoá MCP chỉ đọc silver + gold.' if not failed else f'{failed} mục chưa đạt.'}")
sys.exit(1 if failed else 0)
