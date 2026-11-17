"""Kiểm cơ chế giữ quota: header Meta 80% thì chờ, 96% thì dừng; giãn 10 giây; giờ Phoenix bị chặn;
tối đa 31 ngày; Shopify hết điểm thì chờ; sổ limits.jsonl được ghi. Không gọi mạng, không dùng token.

Chạy từ thư mục gốc:  python tests/test_limits.py
"""

import json
import os
import sys
import tempfile
from argparse import Namespace
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
LOGS = tempfile.mkdtemp()
os.environ["DATAE_LOGS"] = LOGS
os.environ.setdefault("META_ACCESS_TOKEN", "gia")
os.environ.setdefault("META_API_VERSION", "v27.0")

from pipelines import dates, limits  # noqa: E402
from pipelines.sources import meta, shopify  # noqa: E402


class Response:
    def __init__(self, pct, status=200, extra=None):
        self.status_code = status
        self.headers = {"x-business-use-case-usage": json.dumps(
            {"111": [{"type": "ads_insights", "call_count": pct, "total_cputime": 5, "total_time": 5,
                      **(extra or {})}]}),
            "x-app-usage": json.dumps({"call_count": 1, "total_time": 1, "total_cputime": 1})}

    def json(self):
        return {"data": [{"ok": 1}]}


# 1. Đọc header: lấy phần trăm cao nhất và thời gian Meta bảo chờ (phút → giây)
peak, regain = meta.usage(Response(42, extra={"estimated_time_to_regain_access": 2}).headers)
assert (peak, regain) == (42.0, 120.0), (peak, regain)
peak, _ = meta.usage({"x-fb-ads-insights-throttle": json.dumps({"app_id_util_pct": 12, "acc_id_util_pct": 88})})
assert peak == 88.0

sleeps = []
with patch.object(meta.time, "sleep", sleeps.append), patch.object(limits.time, "sleep", sleeps.append):
    # 2. Dưới 50%: không chờ thêm, chỉ giãn nhịp 15 giây giữa 2 lần gọi
    meta.tracker = limits.Tracker("meta", meta.MIN_INTERVAL)
    with patch.object(meta.requests, "get", lambda *a, **k: Response(30)):
        meta.get("x", {})
        meta.get("x", {})
    assert len(sleeps) == 1 and 14 < sleeps[0] <= 15, sleeps

    # 3. 60%: chờ ít nhất 60 giây rồi mới gọi tiếp
    sleeps.clear()
    with patch.object(meta.requests, "get", lambda *a, **k: Response(60)):
        meta.get("x", {})
    assert max(sleeps) >= 60 and meta.tracker.waits == 1, sleeps

    # 4. 80%: dừng hẳn, ghi sổ
    with patch.object(meta.requests, "get", lambda *a, **k: Response(80)):
        try:
            meta.get("x", {})
        except SystemExit as error:
            assert "80%" in str(error.code) and "chưa ghi gì" in str(error.code)
        else:
            raise AssertionError("80% phải dừng")
    record = json.loads((Path(LOGS) / "limits.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["source"] == "meta" and record["peak_pct"] == 80 and "stopped" in record, record

    # 5. Bị Meta chặn (mã 17): chờ đủ 300 giây rồi thử lại
    sleeps.clear()
    replies = iter([type("R", (), {"status_code": 400, "headers": {}, "json": lambda s: {"error": {"code": 17}}})(),
                    Response(10)])
    meta.tracker = limits.Tracker("meta", 0)
    with patch.object(meta.requests, "get", lambda *a, **k: next(replies)):
        assert meta.get("x", {}) == {"data": [{"ok": 1}]}
    assert 300 in sleeps, sleeps

    # 5b. Lỗi tạm của Meta (mã 1 qua HTTP 500, mã 2 qua HTTP 400 như tháng 5/2026): thử lại, không dừng
    sleeps.clear()
    replies = iter([
        type("R", (), {"status_code": 500, "headers": {}, "json": lambda s: {"error": {"code": 1}}})(),
        type("R", (), {"status_code": 400, "headers": {}, "json": lambda s: {"error": {
            "code": 2, "error_subcode": 1504044, "message": "Service temporarily unavailable"}}})(),
        Response(10)])
    with patch.object(meta.requests, "get", lambda *a, **k: next(replies)):
        assert meta.get("x", {}) == {"data": [{"ok": 1}]}
    assert sleeps == [30, 60], sleeps

    # 5c. Lỗi thật (mã 100, sai tham số) thì dừng ngay, không thử lại
    sleeps.clear()
    with patch.object(meta.requests, "get", lambda *a, **k: type("R", (), {
            "status_code": 400, "headers": {}, "json": lambda s: {"error": {"code": 100, "message": "bad"}}})()):
        try:
            meta.get("x", {})
        except SystemExit as error:
            assert "mã 100" in str(error.code)
        else:
            raise AssertionError("mã 100 phải dừng")
    assert sleeps == [], sleeps

    # 5d. Mã 4 (cả app chạm giới hạn, dùng chung với đội ads): dừng ngay, không chờ, không thử lại, ghi sổ
    sleeps.clear()
    tries = []
    with patch.object(meta.requests, "get", lambda *a, **k: tries.append(1) or type("R", (), {
            "status_code": 400, "headers": {"x-app-usage": json.dumps({"call_count": 12}), "x-other": "bo qua"},
            "json": lambda s: {"error": {"code": 4, "message": "Application request limit reached"}}})()):
        try:
            meta.get("x", {})
        except SystemExit as error:
            assert "cả app" in str(error.code) and "đội ads" in str(error.code)
        else:
            raise AssertionError("mã 4 phải dừng")
    assert sleeps == [] and len(tries) == 1, (sleeps, tries)
    record = json.loads((Path(LOGS) / "limits.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert "mã 4" in record.get("stopped", ""), record
    event = json.loads((Path(LOGS) / "limits.jsonl").read_text(encoding="utf-8").splitlines()[-2])
    assert event["event"] and event["code"] == 4 and event["path"] == "x", event
    assert event["headers"] == {"x-app-usage": json.dumps({"call_count": 12})}, "chỉ ghi header mức dùng"

    # 6. Shopify còn 10% điểm: chờ cho hồi tới 50%
    sleeps.clear()
    with patch.object(shopify.time, "sleep", sleeps.append):
        shopify.throttle({"extensions": {"cost": {"throttleStatus": {
            "maximumAvailable": 2000, "currentlyAvailable": 200, "restoreRate": 100}}}})
        shopify.throttle({"extensions": {"cost": {"throttleStatus": {
            "maximumAvailable": 2000, "currentlyAvailable": 1800, "restoreRate": 100}}}})
    assert sleeps == [8.0], sleeps

# 7. Giờ làm việc Phoenix (8–17h) bị chặn, --force thì cho qua
nine_am = datetime(2026, 11, 9, 9, 0, tzinfo=dates.PHOENIX)
nine_pm = datetime(2026, 11, 9, 21, 0, tzinfo=dates.PHOENIX)
try:
    dates.guard_work_hours(False, nine_am)
except SystemExit as error:
    assert "giờ làm việc Phoenix" in str(error.code)
else:
    raise AssertionError("9 giờ sáng Phoenix phải bị chặn")
dates.guard_work_hours(True, nine_am)
dates.guard_work_hours(False, nine_pm)

# 8. Tối đa 31 ngày mỗi lần
done = date(2026, 11, 8)
assert dates.window(Namespace(since=date(2026, 10, 1), until=date(2026, 10, 31)), done)
try:
    dates.window(Namespace(since=date(2026, 9, 1), until=date(2026, 10, 31)), done)
except SystemExit as error:
    assert "tối đa 31 ngày" in str(error.code)
else:
    raise AssertionError("61 ngày phải bị từ chối")

print("PASS: đọc header Meta, giãn 15 giây, 60% chờ, 80% dừng, mã 17 chờ 300 giây, Shopify chờ hồi điểm, "
      "chặn giờ Phoenix, tối đa 31 ngày, ghi sổ limit")
