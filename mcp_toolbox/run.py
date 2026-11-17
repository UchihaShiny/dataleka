"""Chạy MCP Toolbox (bin/toolbox.exe) với khoá CHỈ ĐỌC datae-mcp, đọc từ .env như server datae.

Vì sao không ghi thẳng khoá vào .mcp.json: khoá chỉ khai 1 chỗ (MCP_CREDENTIALS trong .env), và file này TỪ CHỐI
chạy nếu thiếu khoá MCP hoặc khoá trỏ nhầm vào datae-pipeline (có quyền ghi). Cả hai server đều từ chối khóa pipeline.

.mcp.json gọi:  python -m mcp_toolbox.run           (MCP stdio, cho Claude Code)
Thử 1 tool:     python -m mcp_toolbox.run invoke execute_sql "{\"sql\": \"select 1\"}"
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLBOX = ROOT / "bin" / "toolbox.exe"
CONFIG = ROOT / "mcp_toolbox" / "tools.yaml"
sys.path.insert(0, str(ROOT))

from pipelines.bq import MCP_KEY_ENV, settings  # noqa: E402


def toolbox_env() -> dict:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    if not os.environ.get(MCP_KEY_ENV, "").strip():
        sys.exit(f"Chưa có {MCP_KEY_ENV} trong .env: Toolbox chỉ chạy bằng khoá chỉ đọc (docs/cai-dat-bigquery.md mục 8).")
    project, key_path, location = settings(MCP_KEY_ENV)
    email = json.loads(Path(key_path).read_text(encoding="utf-8")).get("client_email", "")
    if not email.startswith("datae-mcp@"):
        sys.exit(f"{MCP_KEY_ENV} phải là khoá datae-mcp (chỉ đọc), đang là {email or 'không rõ'}.")
    if not TOOLBOX.exists():
        sys.exit(f"Chưa có {TOOLBOX}: tải toolbox.exe v1.16.0 theo docs/cai-dat-bigquery.md mục 10.")
    env = dict(os.environ)
    env.update({"GOOGLE_APPLICATION_CREDENTIALS": str(key_path), "BIGQUERY_PROJECT": project,
                "BIGQUERY_LOCATION": location})
    return env


def main(args: list[str]) -> int:
    env = toolbox_env()
    common = ["--config", str(CONFIG), "--disable-version-check"]
    if args and args[0] == "invoke":
        cmd = [str(TOOLBOX), "invoke", *args[1:], *common]
    else:
        cmd = [str(TOOLBOX), *common, "--stdio", *args]
    return subprocess.call(cmd, env=env)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
