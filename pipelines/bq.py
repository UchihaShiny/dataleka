"""Kết nối BigQuery dùng chung: đọc project, khoá, location từ .env."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


MCP_KEY_ENV = "MCP_CREDENTIALS"   # khoá CHỈ ĐỌC silver + gold cho MCP (brief); xem docs/cai-dat-bigquery.md mục 8


def settings(key_env: str = "GOOGLE_APPLICATION_CREDENTIALS") -> tuple[str, Path, str]:
    project = os.environ.get("GCP_PROJECT_ID", "").strip()
    key = os.environ.get(key_env, "").strip()
    location = os.environ.get("BQ_LOCATION", "US").strip() or "US"
    if not project or not key:
        sys.exit(f"Thiếu GCP_PROJECT_ID hoặc {key_env} trong .env. Xem docs/cai-dat-bigquery.md.")
    key_path = Path(key) if Path(key).is_absolute() else ROOT / key
    if not key_path.is_file():
        sys.exit(f"Không thấy file khoá ở {key_path}.")
    return project, key_path, location


def client(key_env: str = "GOOGLE_APPLICATION_CREDENTIALS"):
    from google.cloud import bigquery

    project, key_path, location = settings(key_env)
    return bigquery.Client.from_service_account_json(str(key_path), project=project, location=location)


def mcp_client():
    """Interactive analytics must never fall back to pipeline credentials."""
    if not os.environ.get(MCP_KEY_ENV, "").strip():
        raise RuntimeError("MCP cần MCP_CREDENTIALS chỉ đọc; không dùng khóa pipeline.")
    from dashboard.queries import readonly_client
    return readonly_client()
