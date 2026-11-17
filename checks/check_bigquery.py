"""Kiểm kết nối BigQuery: đọc khoá, chạy select 1, đếm dataset. Chỉ đọc, không tạo gì.

Chạy từ thư mục gốc:  python checks/check_bigquery.py
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
load_dotenv(ROOT / ".env")

MAX_BYTES = 10 * 1024 * 1024  # select 1 quét 0 byte; chặn cứng 10 MB phòng khi sửa nhầm


def fail(message: str) -> None:
    sys.exit(f"LỖI: {message}")


project = os.environ.get("GCP_PROJECT_ID", "").strip()
key_setting = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
location = os.environ.get("BQ_LOCATION", "US").strip() or "US"
missing = [name for name, value in [("GCP_PROJECT_ID", project), ("GOOGLE_APPLICATION_CREDENTIALS", key_setting)] if not value]
if missing:
    fail(f"thiếu trong .env: {', '.join(missing)}. Xem bước 6 trong docs/cai-dat-bigquery.md.")

key_path = Path(key_setting)
if not key_path.is_absolute():
    key_path = ROOT / key_path
if not key_path.is_file():
    fail(f"không thấy file khoá ở {key_path}. Xem bước 5 trong docs/cai-dat-bigquery.md.")

try:
    key = json.loads(key_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    fail(f"{key_path.name} không phải file JSON hợp lệ.")
if key.get("type") != "service_account":
    fail(f"{key_path.name} không phải khoá service account (type = {key.get('type')!r}).")
# Chỉ in email và project của khoá, không bao giờ in private_key
print(f"Service account: {key.get('client_email')}")
if key.get("project_id") != project:
    print(f"  Lưu ý: khoá thuộc project {key.get('project_id')}, còn GCP_PROJECT_ID là {project}")

from google.api_core import exceptions  # noqa: E402
from google.auth.exceptions import GoogleAuthError  # noqa: E402
from google.cloud import bigquery  # noqa: E402

print(f"Project: {project}, location: {location}")

try:
    client = bigquery.Client.from_service_account_json(str(key_path), project=project, location=location)
    job = client.query("select 1 as ok", job_config=bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES))
    value = next(iter(job.result()))["ok"]
    print(f"select 1: {value}, quét {job.total_bytes_processed or 0} byte")
    datasets = [d.dataset_id for d in client.list_datasets()]
except exceptions.Forbidden as error:
    text = str(error)
    if "billing" in text.lower():
        fail(f"BigQuery đòi billing. Sandbox vẫn chạy được select, nên kiểm lại BigQuery API (bước 3).\n  {text[:300]}")
    if "has not been used" in text or "is disabled" in text:
        fail("BigQuery API chưa bật. Xem bước 3.")
    fail(f"không đủ quyền. Kiểm 2 role ở bước 4.\n  {text[:300]}")
except exceptions.NotFound:
    fail(f"không thấy project {project}. Kiểm lại Project ID.")
except (GoogleAuthError, ValueError) as error:
    fail(f"khoá bị từ chối, có thể đã bị xoá hoặc tải nhầm. Tạo khoá mới ở bước 5.\n  {str(error)[:200]}")
except exceptions.GoogleAPICallError as error:
    fail(f"BigQuery báo lỗi: {str(error)[:300]}")

print(f"Dataset hiện có: {len(datasets)}{' (' + ', '.join(datasets) + ')' if datasets else ''}")
print("OK: kết nối BigQuery được")
