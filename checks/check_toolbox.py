"""Kiểm MCP Toolbox (mcp_toolbox/tools.yaml) chạy đúng và CHỈ ĐỌC silver + gold. Dùng khoá datae-mcp.

Đạt khi: đọc được gold và silver (chỉ đếm dòng, không in dữ liệu khách); get_table_info trả mô tả cột (persist_docs);
câu chạm raw, pii bị từ chối; câu CREATE TABLE bị từ chối.
Chạy từ thư mục gốc:  python checks/check_toolbox.py
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from mcp_toolbox.run import CONFIG, TOOLBOX, toolbox_env  # noqa: E402

env = toolbox_env()
P = env["BIGQUERY_PROJECT"]
failed = 0


def invoke(tool: str, params: dict) -> tuple[int, str]:
    r = subprocess.run([str(TOOLBOX), "invoke", tool, json.dumps(params), "--config", str(CONFIG),
                        "--disable-version-check", "--log-level", "ERROR"],
                       env=env, capture_output=True, text=True, encoding="utf-8", timeout=180)
    return r.returncode, (r.stdout + r.stderr).strip()


def check(label: str, ok: bool, detail: str) -> None:
    global failed
    failed += not ok
    print(f"  {'✓' if ok else '✗'} {label}: {detail[:300]}")


def refused(code: int, out: str) -> bool:
    low = out.lower()
    return code != 0 or any(w in low for w in ("error", "denied", "not allowed", "forbidden", "403", "blocked"))


code, out = invoke("execute_sql", {"sql": f"select count(*) as n from `{P}.gold.daily_performance`"})
check("đọc gold.daily_performance", code == 0 and '"n"' in out and not refused(code, out), out)
code, out = invoke("execute_sql", {"sql": f"select count(*) as n from `{P}.silver.stg_orders`"})
check("đọc silver.stg_orders (view → raw)", code == 0 and '"n"' in out and not refused(code, out), out)
code, out = invoke("get_table_info", {"dataset": "gold", "table": "email_daily"})
check("get_table_info có mô tả cột", code == 0 and "attributed" in out, out[:200])
for table in ["raw.shopify_orders", "pii.shopify_customers"]:
    code, out = invoke("execute_sql", {"sql": f"select count(*) as n from `{P}.{table}`"})
    check(f"TỪ CHỐI {table}", refused(code, out) and '"n"' not in out, out)
code, out = invoke("execute_sql", {"sql": f"create table `{P}.gold._toolbox_write_test` as select 1 as x"})
check("TỪ CHỐI create table", refused(code, out), out)

print(f"\n{'Đạt: Toolbox chỉ đọc silver + gold.' if not failed else f'{failed} mục chưa đạt.'}")
sys.exit(1 if failed else 0)
