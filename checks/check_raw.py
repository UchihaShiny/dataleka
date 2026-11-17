"""Kiểm tầng raw đã vào đủ chưa: mỗi bảng cần có của Shopify, Meta, Klaviyo có tồn tại, bao nhiêu dòng,
khoảng ngày có phủ đủ lịch sử theo brief không, khoá chính có trùng không, dữ liệu có mới trong vòng
36 giờ không (brief). Chỉ đọc, giới hạn quét 200 MB.

Chạy từ thư mục gốc:  python checks/check_raw.py
Thoát mã 1 nếu còn bảng thiếu hoặc lỗi.
"""

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "checks"))
sys.stdout.reconfigure(encoding="utf-8")

from google.api_core.exceptions import Forbidden, NotFound  # noqa: E402
from google.cloud import bigquery  # noqa: E402

from pipelines.bq import client  # noqa: E402
from pipelines.dates import FRESH_HOURS, hours_behind  # noqa: E402

from raw_spec import EXPECTED, FRESHNESS  # noqa: E402

CONFIG = bigquery.QueryJobConfig(maximum_bytes_billed=200 * 1024 * 1024)

bq = client()
problems = []
for source, tables in EXPECTED.items():
    print(f"\n== {source} ==")
    for name, (key, date_column, history_from) in tables.items():
        table_id = f"{bq.project}.{name}"
        try:
            table = bq.get_table(table_id)
        except NotFound:
            print(f"  ✗ {name}: chưa có")
            problems.append(f"{name} chưa có")
            continue
        line = f"  {name}: {table.num_rows:,} dòng, nạp lúc {table.modified:%Y-%m-%d %H:%M} UTC"
        if table.num_rows == 0:
            problems.append(f"{name} rỗng")
        duplicates = next(iter(bq.query(
            f"select count(*) from (select 1 from `{table_id}` group by {key} having count(*) > 1)",
            job_config=CONFIG).result()))[0]
        line += f", khoá trùng: {duplicates}"
        if duplicates:
            problems.append(f"{name} có {duplicates} khoá trùng")
        if date_column:
            first, last = next(iter(bq.query(
                f"select date(min({date_column})), date(max({date_column})) from `{table_id}`",
                job_config=CONFIG).result()))
            line += f", từ {first} đến {last}"
            if history_from and first and first > history_from:
                problems.append(f"{name} bắt đầu từ {first}, cần từ {history_from} hoặc sớm hơn")
        print(("  ✓" if not any(name in p for p in problems) else "  !") + line[1:])

print()
print(f"== Độ mới (brief: trong vòng {FRESH_HOURS} giờ) ==")
for source, (name, expression) in FRESHNESS.items():
    try:
        latest = next(iter(bq.query(f"select {expression} from `{bq.project}.{name}`", job_config=CONFIG).result()))[0]
    except NotFound:
        continue
    if latest is None:
        continue
    behind = hours_behind(latest)
    ok = behind <= FRESH_HOURS
    print(f"  {'✓' if ok else '✗'} {source}: mới nhất {latest}, trễ {behind:.0f} giờ")
    if not ok:
        problems.append(f"{source} trễ {behind:.0f} giờ (quá {FRESH_HOURS} giờ)")

# Giới hạn Sandbox: 10 GB lưu trữ, 1 TB truy vấn mỗi tháng
STORAGE_WARN_GB, QUERY_WARN_GB = 8, 800
stored = sum(bq.get_table(t).num_bytes or 0 for d in ("raw", "silver", "gold", "pii") for t in bq.list_tables(d))
print("\n== BigQuery Sandbox ==")
print(f"  Lưu trữ: {stored / 1024**2:,.1f} MB / 10 GB")
if stored > STORAGE_WARN_GB * 1024**3:
    problems.append(f"lưu trữ {stored / 1024**3:.1f} GB, gần trần 10 GB của Sandbox")
# Đọc lịch sử truy vấn cần quyền bigquery.jobs.list (role BigQuery Resource Viewer); thiếu thì bỏ qua.
# Lớp bảo vệ chính vẫn là maximum_bytes_billed trên từng truy vấn.
try:
    billed = next(iter(bq.query(
        f"select coalesce(sum(total_bytes_billed), 0) from `region-{bq.location.lower()}`.INFORMATION_SCHEMA.JOBS_BY_USER "
        "where creation_time >= timestamp_trunc(current_timestamp(), month) and job_type = 'QUERY'",
        job_config=CONFIG).result()))[0]
    print(f"  Truy vấn tháng này (pipeline): {billed / 1024**3:,.3f} GB / 1 TB")
    if billed > QUERY_WARN_GB * 1024**3:
        problems.append(f"đã quét {billed / 1024**3:.0f} GB trong tháng, gần trần 1 TB")
except Forbidden:
    print("  Truy vấn tháng này: chưa đo được (service account thiếu quyền bigquery.jobs.list)")

print()
if problems:
    print("CHƯA ĐỦ:")
    for problem in problems:
        print(f"  - {problem}")
    sys.exit(1)
print(f"OK: raw đã có đủ Shopify, Meta, Klaviyo, không trùng khoá, dữ liệu mới trong vòng {FRESH_HOURS} giờ")
