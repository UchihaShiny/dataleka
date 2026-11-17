"""In TÊN các biến trong .env (KHÔNG in giá trị), để soát thiếu hay gõ sai tên mà không lộ khoá.

Chạy từ thư mục gốc:  python checks/check_env_names.py
"""

import sys
from pathlib import Path

from dotenv import dotenv_values

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
env = ROOT / ".env"
if not env.is_file():
    sys.exit(f"Không thấy {env}")
values = dotenv_values(env)
print(f"{env} ({env.stat().st_size} byte, sửa lần cuối "
      f"{__import__('datetime').datetime.fromtimestamp(env.stat().st_mtime):%d/%m %H:%M}), {len(values)} biến:")
SAFE = {"GCP_PROJECT_ID", "GOOGLE_APPLICATION_CREDENTIALS", "MCP_CREDENTIALS", "BQ_LOCATION"}  # không phải bí mật
for name, value in values.items():
    shown = repr(value) if name in SAFE else ("có giá trị" if value else "TRỐNG")
    print(f"  {name!r}: {shown}")
lines = env.read_text(encoding="utf-8-sig").splitlines()
commented = [ln.split("=")[0].lstrip("# ").strip() for ln in lines if ln.lstrip().startswith("#") and "=" in ln]
if commented:
    print(f"Dòng bị chú thích (#), không có hiệu lực: {', '.join(commented)}")
if values.get("BQ_LOCATION") not in (None, "US"):
    print("⚠ BQ_LOCATION khác 'US': có thể dòng mới bị dính vào cuối dòng BQ_LOCATION (thiếu xuống dòng).")
mcp = values.get("MCP_CREDENTIALS")
if mcp is None:
    near = [n for n in values if "MCP" in n.upper() or "CRED" in n.upper()]
    print(f"\nChưa có biến MCP_CREDENTIALS.{' Tên gần giống: ' + ', '.join(map(repr, near)) if near else ''}")
else:
    path = Path(mcp) if Path(mcp).is_absolute() else ROOT / mcp
    print(f"\nMCP_CREDENTIALS có; file khoá {'CÓ' if path.is_file() else 'KHÔNG THẤY'} ở {path}")
