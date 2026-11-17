"""Kiểm hàm so số của checks/reconcile.py. Không gọi mạng.

Chạy từ thư mục gốc:  python tests/test_reconcile.py
"""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "checks"))
sys.stdout.reconfigure(encoding="utf-8")

import reconcile  # noqa: E402

# Đếm đơn phải bằng đúng
assert reconcile.compare({"2026-10": 3016, "2026-11": 927}, {"2026-10": 3016, "2026-11": 927}) == []
assert reconcile.compare({"2026-10": 3016}, {"2026-10": 3015}) == [("2026-10", 3016, 3015)]
# Kỳ chỉ có ở một bên cũng là lệch
assert reconcile.compare({"2026-09": 5}, {}) == [("2026-09", 5, 0)]
# Tiền: lệch 0,001% vẫn đạt với ngưỡng 0,01%; lệch 1% thì không
tol = reconcile.MONEY_TOLERANCE / 100
assert reconcile.compare({"d": Decimal("4175.15")}, {"d": Decimal("4174.92")}, tol) == []
assert reconcile.compare({"d": Decimal("100")}, {"d": Decimal("99")}, tol) != []
# Meta: chênh 0,52 USD (đúng ca 23/10) đạt với ngưỡng 1 USD; chênh 5 USD thì không
assert reconcile.compare({"d": Decimal("3190.84")}, {"d": Decimal("3190.32")}, tol, reconcile.META_DAILY_ABS) == []
assert reconcile.compare({"d": Decimal("3190.84")}, {"d": Decimal("3185.84")}, tol, reconcile.META_DAILY_ABS) != []
# Chia tháng
assert list(reconcile.month_starts(date(2026, 10, 15), date(2026, 11, 2))) == [
    (date(2026, 10, 1), date(2026, 11, 1)), (date(2026, 11, 1), date(2026, 12, 1))]
assert reconcile.phoenix_range(date(2026, 10, 1), date(2026, 11, 1)) == (
    "created_at:>='2026-10-01T00:00:00-07:00' created_at:<'2026-11-01T00:00:00-07:00'")
# Tháng đang chạy: cắt ở đơn mới nhất kho đã có; tháng cũ thì không cắt
assert reconcile.phoenix_range(date(2026, 11, 1), date(2026, 12, 1), "2026-11-09T03:47:09Z") == (
    "created_at:>='2026-11-01T00:00:00-07:00' created_at:<'2026-11-09T03:47:09Z'")
assert reconcile.phoenix_range(date(2026, 10, 1), date(2026, 11, 1), "2026-11-09T03:47:09Z").endswith("'2026-11-01T00:00:00-07:00'")

# Khoảng so: mặc định 7 ngày đã trọn, --since/--until đúng khoảng vừa nạp, --all là cả kho
import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402
from unittest.mock import patch  # noqa: E402

A = lambda **k: argparse.Namespace(**{"since": None, "until": None, "all": False, **k})  # noqa: E731
done = date(2026, 11, 9)
assert reconcile.span(A(), done) == (date(2026, 11, 3), date(2026, 11, 9))
assert reconcile.span(A(since=date(2026, 3, 1), until=date(2026, 3, 31)), done) == (date(2026, 3, 1), date(2026, 3, 31))
assert reconcile.span(A(all=True), done) is None
for bad in (A(all=True, since=date(2026, 3, 1)), A(since=date(2026, 4, 1), until=date(2026, 3, 1))):
    try:
        reconcile.span(bad, done)
    except SystemExit:
        pass
    else:
        raise AssertionError("phải từ chối")
assert reconcile.between("date", None) == ""

# Meta chỉ hỏi lại đúng tháng vừa nạp: 1 lần lấy tài khoản + 1 lần insights, kho cũng chỉ lấy khoảng đó
os.environ["DATAE_LOGS"] = tempfile.mkdtemp()
os.environ.setdefault("META_ACCESS_TOKEN", "gia")
os.environ.setdefault("META_API_VERSION", "v27.0")
from pipelines.sources import meta  # noqa: E402

calls, sqls = [], []


def fake_get_all(path, params):
    calls.append((path, params))
    span = json.loads(params["time_range"])
    return [{"date_start": span["since"], "spend": "10.00"}]


def fake_bq(sql):
    sqls.append(sql)
    return {"111 2026-03-01": Decimal("10.00")}


with patch.object(meta, "ad_accounts", lambda a, b: calls.append(("accounts", (a, b))) or ([], [{"account_id": "111"}])), \
        patch.object(meta, "get_all", fake_get_all), patch.object(reconcile, "bq_rows", fake_bq):
    assert reconcile.check_meta((date(2026, 3, 1), date(2026, 3, 31))) is True
assert calls[0] == ("accounts", (date(2026, 3, 1), date(2026, 3, 31))) and len(calls) == 2, calls
assert json.loads(calls[1][1]["time_range"]) == {"since": "2026-03-01", "until": "2026-03-31"}
assert len(sqls) == 1 and "between '2026-03-01' and '2026-03-31'" in sqls[0], sqls
print("PASS: bộ lọc tháng theo giờ Phoenix, so số đếm, so tiền có ngưỡng, kỳ thiếu một bên, chia tháng, "
      "chỉ so khoảng vừa nạp (Meta 2 lần gọi cho 1 tháng)")
