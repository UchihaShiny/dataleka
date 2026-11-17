"""Kiểm nguồn Klaviyo bằng phản hồi giả: phân trang links.next, campaign message, metric aggregates
theo ngày × message, cache theo ngày, chạy lại không trùng. Không gọi Klaviyo, không dùng khoá GCP.

Chạy từ thư mục gốc:  python tests/test_klaviyo.py
"""

import json
import sys
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.stdout.reconfigure(encoding="utf-8")
import os  # noqa: E402
os.environ["DATAE_LOGS"] = tempfile.mkdtemp()  # không ghi vào sổ limit thật

from pipelines import common  # noqa: E402
from pipelines.sources import klaviyo as source  # noqa: E402
from test_common import FakeBigQuery  # noqa: E402

bodies = []


def fake_call(method, url, params=None, data=None):
    if method == "POST":
        assert url.endswith("/metric-aggregates")
        body = json.loads(data)["data"]["attributes"]
        bodies.append(body)
        assert body["timezone"] == "America/Phoenix" and body["interval"] == "day"
        assert all(f.endswith("T00:00:00-07:00)") for f in body["filter"]), "bộ lọc phải theo giờ Phoenix"
        start = body["filter"][0].split(",")[1][:10]
        dates = [f"{start[:8]}{int(start[8:]) + i:02d}T00:00:00-07:00" for i in range(3)]
        groups = [{"dimensions": ["msgA"], "measurements": {"count": [5, 0, 2]}},
                  {"dimensions": [""], "measurements": {"count": [1, 1, 1]}}]
        if "sum_value" in body["measurements"]:
            groups[0]["measurements"]["sum_value"] = [100.5, 0, 7260.470000000001]
            groups[1]["measurements"]["sum_value"] = [10.0, 10.0, 10.0]
        return {"data": {"attributes": {"dates": dates, "data": groups}}}
    if url.endswith("/campaigns"):
        assert "filter" not in params, "revision mới không cho lọc messages.channel"
        return {"data": [{"id": "c1", "attributes": {
                    "created_at": "2026-10-20T00:00:00+00:00", "updated_at": "2026-11-01T00:00:00+00:00",
                    "definition": {"name": "Black Friday", "builder": "email", "archived": False,
                                   "send_settings": {"send_timezone": "America/Phoenix", "send_strategy": "static"}}},
                          "relationships": {"campaign-messages": {"data": [{"type": "campaign-message", "id": "msgA"}]}}}],
                "included": [{"type": "campaign-message", "id": "msgA", "attributes": {
                    "created": "2026-10-20T00:00:00+00:00", "updated": "2026-11-01T00:00:00+00:00",
                    "definition": {"name": "BF email", "status": "Sent",
                                   "send_options": {"send_time": "2026-11-01T15:00:00+00:00", "send_strategy": "static"}}}}],
                "links": {"next": "https://a.klaviyo.com/api/campaigns?page%5Bcursor%5D=2"}}
    if "page%5Bcursor%5D=2" in url:
        return {"data": [{"id": "c2", "attributes": {"definition": {"name": "Cyber", "builder": "email"}}}],
                "links": {"next": None}}
    if url.endswith("/flows/f1/flow-actions"):
        return {"data": [{"id": "a1"}, {"id": "a2"}]}
    if url.endswith("/flow-actions/a1/flow-messages"):
        return {"data": [{"id": "fm1", "attributes": {"definition": {"name": "Welcome 1", "channel": "email"},
                                                        "created": "2026-01-01T00:00:00+00:00"}}]}
    if url.endswith("/flow-actions/a2/flow-messages"):
        # fm1 lặp lại dưới action a2 như A/B test thật của DEERLY
        return {"data": [{"id": "fm2", "attributes": {"name": "Welcome 2", "channel": "email"}},
                         {"id": "fm1", "attributes": {"definition": {"name": "Welcome 1", "channel": "email"}}}]}
    if url.endswith("/flows"):
        return {"data": [{"id": "f1", "attributes": {"name": "Welcome", "status": "live", "trigger_type": "List"}}]}
    if url.endswith("/metrics"):
        return {"data": [{"id": f"m{i}", "attributes": {"name": n, "integration": {"name": "Klaviyo"}}}
                         for i, n in enumerate(["Received Email", "Opened Email", "Clicked Email",
                                                "Placed Order", "Viewed Product"])]}
    raise AssertionError(f"gọi lạ: {method} {url}")


with tempfile.TemporaryDirectory() as folder, patch.object(source, "call", fake_call):
    data_dir, bq, cache = Path(folder), FakeBigQuery(), Path(folder) / "kcache"
    for attempt in (1, 2):
        loaded = common.run(source.klaviyo(date(2026, 11, 1), date(2026, 11, 3), cache), "klaviyo", "klaviyo",
                            bq=bq, data_dir=data_dir)
    # 4 metric × (msgA 2 ngày khác 0 + rỗng 3 ngày) = 20 dòng
    assert loaded == {"campaigns": 2, "campaign_messages": 1, "flows": 1, "flow_messages": 2, "metrics": 5,
                      "message_daily": 20}, loaded
    fms = source.fetch_flow_messages([{"flow_id": "f1"}])
    assert [(m["message_id"], m["flow_id"], m["name"], m["action_ids"]) for m in fms] == [
        ("fm1", "f1", "Welcome 1", "a1,a2"), ("fm2", "f1", "Welcome 2", "a2")], fms
    assert (cache / ".." / "flow_messages.json").resolve().is_file(), "phải lưu cache flow messages"
    assert len(bodies) == 8, "mỗi lần chạy 4 metric, không gọi Viewed Product"
    assert [b["by"] for b in bodies[:4]] == [["$message"]] * 3 + [["$attributed_message"]]
    assert "sum_value" in bodies[3]["measurements"] and "sum_value" not in bodies[0]["measurements"]

    campaigns, messages = source.fetch_campaigns()
    assert campaigns[0]["name"] == "Black Friday" and campaigns[1]["name"] == "Cyber", campaigns
    assert messages == [{"message_id": "msgA", "campaign_id": "c1", "name": "BF email", "status": "Sent",
                         "send_time": "2026-11-01T15:00:00+00:00", "send_strategy": "static",
                         "created_at": "2026-10-20T00:00:00+00:00", "updated_at": "2026-11-01T00:00:00+00:00"}], messages
    rows = list(source.cached_message_daily(cache))
    order_value = sum(r["value"] for r in rows if r["metric"] == "placed_order")
    assert order_value == Decimal("7390.97"), order_value
    assert all(r["value"] is None or -r["value"].as_tuple().exponent <= 2 for r in rows), "tiền phải 2 chữ số thập phân"
    assert {r["message_id"] for r in rows} == {"msgA", "(none)"}
    schema = bq.schemas["gia-lap.raw.klaviyo_message_daily"]
    assert schema["date"] == "DATE" and schema["count"] == "INT64" and schema["value"] == "NUMERIC", schema
    for table in bq.tables:
        assert not table.startswith("gia-lap.pii"), "Klaviyo không được tạo bảng PII"
print("PASS: Klaviyo phân trang, campaign message, flow message, đếm theo ngày × message, cache, chạy lại không trùng")
