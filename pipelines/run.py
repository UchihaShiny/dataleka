"""Một lệnh chạy cả hệ: Shopify → Meta → Klaviyo → kiểm raw → dbt build → dự báo. Bước nào lỗi thì dừng.
(13/11: thêm dbt build và forecast.publish ở cuối để dự báo tự cập nhật sau mỗi lần nạp; dự báo đọc gold nên phải
sau dbt build. Reconcile vẫn chạy riêng: python checks/reconcile.py.)

Mỗi bước chạy thành tiến trình riêng nên lỗi của bước này không làm hỏng dữ liệu bước khác.
Mỗi lần chạy ghi 1 dòng vào logs/runs.jsonl: thời điểm, từng bước đạt hay lỗi, thời gian, số dòng.
Dùng token Shopify, Meta, Klaviyo và khoá GCP.

Chạy từ thư mục gốc:
  python -m pipelines.run                  7 ngày đã trọn gần nhất cho Meta, Klaviyo
  python -m pipelines.run --since 2026-09-01 --until 2026-09-30   một khoảng cho Meta, Klaviyo
  python -m pipelines.run --skip shopify   bỏ một bước (shopify, meta, klaviyo, dbt, forecast)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from pipelines.dates import guard_work_hours  # noqa: E402

SOURCES = ["shopify", "meta", "klaviyo"]
AFTER = ["dbt", "forecast"]   # bước sau tầng raw, bỏ được bằng --skip


def steps(args) -> list[tuple[str, list[str]]]:
    window = ["--since", str(args.since), "--until", str(args.until)] if args.since else []
    force = ["--force"] if args.force else []
    plan = []
    if "shopify" not in args.skip:
        plan.append(("shopify", ["-m", "pipelines.load_shopify"]))
    if "meta" not in args.skip:
        plan.append(("meta", ["-m", "pipelines.load_meta", *window, *force]))
    if "klaviyo" not in args.skip:
        plan.append(("klaviyo", ["-m", "pipelines.load_klaviyo", *window, *force]))
    plan.append(("check_raw", ["checks/check_raw.py"]))
    if "dbt" not in args.skip:
        plan.append(("dbt", ["-m", "pipelines.dbt", "build"]))
    if "forecast" not in args.skip:
        plan.append(("forecast", ["-m", "forecast.publish"]))
    return plan


def run_step(name: str, command: list[str]) -> dict:
    """Chạy một bước, vừa in ra màn hình vừa giữ dòng OK cuối để ghi log."""
    print(f"\n######## {name} ########", flush=True)
    started = time.monotonic()
    # PYTHONUNBUFFERED: không có thì tiến trình con giữ chữ trong bộ đệm, màn hình trông như bị treo
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    process = subprocess.Popen([sys.executable, *command], cwd=ROOT, env=env, text=True, encoding="utf-8",
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    summary = None
    for line in process.stdout:
        print(line, end="", flush=True)
        if line.startswith(("OK:", "meta:", "klaviyo:", "shopify:", "Mốc ")) or "Done. PASS=" in line:
            summary = (summary + " | " if summary else "") + line.strip()
    process.wait()
    return {"step": name, "ok": process.returncode == 0, "seconds": round(time.monotonic() - started, 1),
            "summary": summary}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", type=date.fromisoformat)
    parser.add_argument("--until", type=date.fromisoformat)
    parser.add_argument("--skip", nargs="*", default=[], choices=SOURCES + AFTER)
    parser.add_argument("--force", action="store_true", help="chạy cả trong giờ làm việc Phoenix (đã báo anh)")
    args = parser.parse_args(argv)
    if bool(args.since) != bool(args.until):
        parser.error("cần cả --since và --until")
    if {"meta", "klaviyo"} - set(args.skip):
        guard_work_hours(args.force)  # kiểm trước, khỏi chạy Shopify xong mới bị chặn

    started_at = datetime.now(timezone.utc)
    plan = steps(args)
    results = []
    for name, command in plan:
        result = run_step(name, command)
        results.append(result)
        if not result["ok"]:
            break

    failed = next((r["step"] for r in results if not r["ok"]), None)
    record = {"at": started_at.isoformat(timespec="seconds"), "ok": failed is None, "failed_step": failed,
              "skipped": [name for name, _ in plan[len(results):]], "since": str(args.since or ""),
              "until": str(args.until or ""), "steps": results}
    logs = Path(os.environ.get("DATAE_LOGS") or ROOT / "logs")
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / "runs.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    print("\n######## Tóm tắt ########")
    for r in results:
        print(f"  {'OK ' if r['ok'] else 'LỖI'} {r['step']} ({r['seconds']} giây)")
    if failed:
        print(f"Dừng ở bước {failed}. Bỏ qua: {', '.join(record['skipped']) or 'không có'}")
        return 1
    print("Xong: raw đủ và đúng" + ("" if "dbt" in args.skip else ", gold đã dựng lại")
          + ("" if "forecast" in args.skip else ", dự báo đã cập nhật"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
