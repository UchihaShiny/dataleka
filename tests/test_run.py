"""Kiểm lệnh chạy cả tầng raw: đúng thứ tự, truyền đúng tham số, dừng ở bước lỗi, ghi log.
Thay các bước thật bằng lệnh python giả, không gọi API, không dùng khoá.

Chạy từ thư mục gốc:  python tests/test_run.py
"""

import json
import os
import sys
import tempfile
from argparse import Namespace
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")
LOGS = tempfile.mkdtemp()
os.environ["DATAE_LOGS"] = LOGS

from pipelines import dates, run  # noqa: E402

# Thứ tự và tham số
plan = run.steps(Namespace(since=date(2026, 9, 1), until=date(2026, 9, 30), skip=[], force=False))
assert [name for name, _ in plan] == ["shopify", "meta", "klaviyo", "check_raw", "dbt", "forecast"]
assert plan[4][1] == ["-m", "pipelines.dbt", "build"] and plan[5][1] == ["-m", "forecast.publish"], "dự báo sau dbt build"
assert plan[1][1] == ["-m", "pipelines.load_meta", "--since", "2026-09-01", "--until", "2026-09-30"]
assert "--since" not in plan[0][1], "Shopify không nhận khoảng ngày"
plan = run.steps(Namespace(since=None, until=None, skip=["shopify"], force=True))
assert [name for name, _ in plan] == ["meta", "klaviyo", "check_raw", "dbt", "forecast"] and "--force" in plan[0][1]
plan = run.steps(Namespace(since=None, until=None, skip=["dbt", "forecast"], force=False))
assert [name for name, _ in plan] == ["shopify", "meta", "klaviyo", "check_raw"], "bỏ được dbt, forecast"

# Dừng ở bước lỗi, các bước sau không chạy, log ghi đủ
fake = [("shopify", ["-c", "print('OK: orders 3')"]), ("meta", ["-c", "import sys; sys.exit(2)"]),
        ("klaviyo", ["-c", "print('không được chạy')"]), ("check_raw", ["-c", "print('x')"])]
evening = datetime(2026, 11, 9, 20, 0, tzinfo=dates.PHOENIX)
with patch.object(run, "steps", lambda args: fake), \
        patch.object(dates, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: evening)})):
    code = run.main([])
assert code == 1
record = json.loads((Path(LOGS) / "runs.jsonl").read_text(encoding="utf-8").splitlines()[-1])
assert record["failed_step"] == "meta" and record["skipped"] == ["klaviyo", "check_raw"], record
assert record["steps"][0]["summary"] == "OK: orders 3"

# Giờ làm việc Phoenix: chặn ngay từ đầu, không chạy bước nào
morning = datetime(2026, 11, 9, 10, 0, tzinfo=dates.PHOENIX)
with patch.object(run, "steps", lambda args: fake), \
        patch.object(dates, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: morning)})):
    try:
        run.main([])
    except SystemExit as error:
        assert "giờ làm việc Phoenix" in str(error.code)
    else:
        raise AssertionError("phải chặn trong giờ làm việc Phoenix")
assert len((Path(LOGS) / "runs.jsonl").read_text(encoding="utf-8").splitlines()) == 1, "bị chặn thì chưa chạy gì"
print("PASS: thứ tự bước, tham số, dừng ở bước lỗi, log runs.jsonl, chặn giờ Phoenix")
