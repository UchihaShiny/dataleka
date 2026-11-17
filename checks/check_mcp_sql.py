"""Kiểm mọi câu SQL của MCP server trên BigQuery THẬT bằng dry run (BigQuery chỉ kiểm cú pháp, tên bảng, tên cột,
kiểu tham số; không chạy, không quét byte nào, không tốn tiền).

Vì sao: tests/test_mcp_server.py dùng BigQuery giả, không biết cột có thật không. Script này bắt lỗi đó trước
khi mở phiên Claude mới. Dùng khoá GCP (chỉ đọc). Chạy từ thư mục gốc:  python checks/check_mcp_sql.py
"""

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from google.cloud import bigquery  # noqa: E402

from mcp_server import server as s  # noqa: E402
from pipelines.bq import mcp_client  # noqa: E402

DAYS = {"since": date(2026, 11, 4), "until": date(2026, 11, 10)}
CASES = {
    "daily_performance": (s.DAILY_SQL, DAYS),
    "performance_summary": (s.SUMMARY_SQL, DAYS),
    "type_performance": (s.TYPE_SQL, DAYS),
    "product_performance": (s.PRODUCT_SQL, {**DAYS, "product_line": ""}),
    "email_performance": (s.EMAIL_SQL, {**DAYS, "channel": ""}),
    "customer_summary": (s.CUSTOMER_SQL, {"cohort_from": "2026-01", "cohort_to": "2026-11"}),
    "rfm_segments": (s.RFM_SQL, {}),
    "product_abc (nhóm)": (s.ABC_SUMMARY_SQL, {"product_line": ""}),
    "product_abc (top)": (s.ABC_TOP_SQL, {"product_line": "", "top": 20}),
    "product_abc (mới)": (s.ABC_NEW_SQL, {"product_line": ""}),
    "product_abc (gini)": (s.ABC_GINI_SQL, {"product_line": ""}),
    "product_abc (xyz)": (s.ABC_XYZ_SQL, {"product_line": ""}),
    "anomaly_check": (s.ANOMALY_SQL, {"until": "", "span": 6}),
    "forecast_orders (ets)": (s.FORECAST_SQL, {}),
    "forecast_orders (spend)": (s.SPEND_MODEL_SQL, {}),
    "forecast_orders (sự kiện)": (s.EVENTS_SQL, {"since": date(2026, 11, 12), "until": date(2026, 11, 25)}),
    "forecast_orders (pacing)": (s.MTD_SQL, {"month_start": date(2026, 11, 1), "until": date(2026, 11, 10)}),
    "clv_summary": (s.CLV_SQL, {"cohort_from": "2024-11", "cohort_to": "2026-11", "max_offset": 6}),
    "cohort_retention": (s.COHORT_SQL, {"cohort_from": "2026-01", "cohort_to": "2026-11", "max_offset": 6}),
    **{f"ad_performance ({level})": (s.AD_SQL.replace("{cols}", cols), {**DAYS, "top": 20, "product_line": "", "campaign": ""})
       for level, cols in s.AD_LEVELS.items()},
}

bq = mcp_client()   # cùng khoá với MCP thật, để dry run cũng kiểm quyền đọc
failed = 0
for name, (sql, params) in CASES.items():
    config = bigquery.QueryJobConfig(
        dry_run=True, use_query_cache=False,
        query_parameters=[bigquery.ScalarQueryParameter(k, s.param_type(v), v) for k, v in params.items()])
    try:
        job = bq.query(sql.replace("{p}", bq.project), job_config=config)
        print(f"  ✓ {name}: sẽ quét {job.total_bytes_processed / 1024 / 1024:.1f} MB (giới hạn 200 MB)")
        if job.total_bytes_processed > s.MAX_BYTES:
            failed += 1
            print("    ✗ vượt giới hạn quét")
    except Exception as error:  # in lý do để sửa
        failed += 1
        print(f"  ✗ {name}: {str(error)[:300]}")

print(f"\n{len(CASES) - failed}/{len(CASES)} câu SQL hợp lệ.")
sys.exit(1 if failed else 0)
