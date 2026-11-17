"""Kiểm nguồn Meta bằng phản hồi giả: chia tháng, phân trang, cache theo ngày, chạy lại không trùng,
chặn ngày chưa trọn, cột actions là JSON. Không gọi Meta, không dùng khoá GCP.

Chạy từ thư mục gốc:  python tests/test_meta.py
"""

import argparse
import json
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.stdout.reconfigure(encoding="utf-8")
import os  # noqa: E402
os.environ["DATAE_LOGS"] = tempfile.mkdtemp()  # không ghi vào sổ limit thật

from pipelines import common  # noqa: E402
from pipelines import load_meta  # noqa: E402
from pipelines.sources import meta as source  # noqa: E402
from test_common import FakeBigQuery  # noqa: E402

calls = []


def fake_get(path, params):
    calls.append((path, dict(params)))
    if path == "me/adaccounts":
        assert "insights.time_range(" in params["fields"], "phải lấy spend cùng danh sách tài khoản"
        return {"data": [{"account_id": "111", "name": "A", "currency": "USD", "timezone_name": "America/Phoenix",
                          "insights": {"data": [{"spend": "123.45"}]}},
                         {"account_id": "222", "name": "Rỗng", "currency": "USD", "timezone_name": "America/Phoenix"}]}
    account = path.split("_")[1].split("/")[0]
    if path.endswith("/ads"):
        assert "effective_status" not in params, "Meta v27 không nhận danh sách trạng thái"
        assert "ids" not in params
        if account == "222":
            return {"data": []}
        return {"data": [{"id": f"ad{i}", "name": f"Ad {i}", "created_time": "2026-01-01T00:00:00-0700",
                          "effective_status": "ACTIVE", "adset": {"id": "s1", "name": "Set"},
                          "campaign": {"id": "c1", "name": "Camp", "objective": "OUTCOME_SALES"},
                          "creative": {"id": f"cr{i}"}} for i in range(2)]}
    assert path.endswith("/insights") and params["level"] == "ad" and params["time_increment"] == 1
    if account == "222":
        return {"data": []}
    span = json.loads(params["time_range"])
    start, end = date.fromisoformat(span["since"]), date.fromisoformat(span["until"])
    assert start.month == end.month, "mỗi lần gọi chỉ một tháng"
    assert (end - start).days <= 6, "mỗi lần gọi tối đa 7 ngày"
    rows = []
    day = start
    while day <= end:
        for i in range(2):
            rows.append({"date_start": str(day), "date_stop": str(day), "account_id": "111",
                         "campaign_id": "c1", "campaign_name": "Camp", "adset_id": "s1", "adset_name": "Set",
                         "ad_id": f"ad{i}", "ad_name": f"Ad {i}", "spend": "10.50", "impressions": "1000",
                         "reach": "800", "clicks": "20", "inline_link_clicks": "12",
                         "actions": [{"action_type": "purchase", "value": "1"}],
                         "action_values": [{"action_type": "purchase", "value": "45.10"}]})
        day += timedelta(days=1)
    # Trả 2 trang để kiểm phân trang
    half = len(rows) // 2
    if "after" not in params:
        return {"data": rows[:half], "paging": {"next": "x", "cursors": {"after": "p2"}}}
    return {"data": rows[half:], "paging": {}}


with tempfile.TemporaryDirectory() as folder, patch.object(source, "get", fake_get):
    data_dir, bq = Path(folder), FakeBigQuery()
    cache = data_dir / "meta_cache"

    # Backfill 20/9 đến 10/10: 2 tháng, 21 ngày × 2 ad
    loaded = common.run(source.meta(date(2026, 9, 20), date(2026, 10, 10), cache), "meta", "meta", bq=bq,
                        data_dir=data_dir)
    assert loaded == {"ad_insights_daily": 42, "ads": 2}, loaded
    assert len(list(cache.glob("*.json"))) == 21
    windows = sorted(tuple(json.loads(p["time_range"]).values()) for path, p in calls
                     if path.endswith("insights") and "after" not in p)
    assert windows == [("2026-09-20", "2026-09-26"), ("2026-09-27", "2026-09-30"),
                       ("2026-10-01", "2026-10-07"), ("2026-10-08", "2026-10-10")], windows
    assert not any("act_222" in path for path, _ in calls), "tài khoản không có spend thì không gọi insights"
    assert sum(1 for path, _ in calls if path.endswith("/ads")) == 1

    # Lần chạy hằng ngày: chỉ gọi Meta cho 7 ngày, nhưng bảng vẫn đủ lịch sử, không trùng
    calls.clear()
    loaded = common.run(source.meta(date(2026, 10, 4), date(2026, 10, 10), cache), "meta", "meta", bq=bq,
                        data_dir=data_dir)
    assert loaded["ad_insights_daily"] == 42, loaded
    assert {json.loads(p["time_range"])["since"] for path, p in calls if path.endswith("insights")} == {"2026-10-04"}
    assert not any(path.endswith("/ads") for path, _ in calls), "cây ad còn mới (< 24 giờ) thì không gọi lại"

    # Lấy thêm ngày mới thì bảng dài thêm đúng số dòng của ngày đó
    loaded = common.run(source.meta(date(2026, 10, 11), date(2026, 10, 11), cache), "meta", "meta", bq=bq,
                        data_dir=data_dir)
    assert loaded["ad_insights_daily"] == 44, loaded

    schema = bq.schemas["gia-lap.raw.meta_ad_insights_daily"]
    assert schema["actions"] == "JSON" and schema["action_values"] == "JSON", schema
    assert schema["spend"] == "NUMERIC" and schema["date"] == "DATE" and schema["impressions"] == "INT64", schema

# Khoảng ngày: mặc định 7 ngày đã trọn theo Phoenix, chặn ngày chưa kết thúc
done = load_meta.last_complete_day(datetime(2026, 11, 9, 5, 0, tzinfo=load_meta.PHOENIX))
assert done == date(2026, 11, 8)
args = argparse.Namespace(since=None, until=None)
assert load_meta.window(args, done) == (date(2026, 11, 2), date(2026, 11, 8))
try:
    load_meta.window(argparse.Namespace(since=date(2026, 11, 1), until=date(2026, 11, 9)), done)
except SystemExit as error:
    assert "chưa kết thúc" in str(error.code)
else:
    raise AssertionError("phải chặn ngày chưa trọn")
print("PASS: Meta chia tuần trong từng tháng, phân trang, cache theo ngày, chạy lại không trùng, chặn ngày chưa trọn, JSON đúng")
