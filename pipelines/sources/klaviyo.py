"""Nguồn dlt cho Klaviyo: campaigns (kèm message), flows, metrics và số đếm theo ngày × message.

Không kéo từng event thô (có thể hàng triệu dòng và có email người nhận). Thay vào đó dùng
Query Metric Aggregates: mỗi ngày Phoenix, mỗi message một dòng số received, open, click và
số đơn, doanh thu attributed. Không có PII. POST metric-aggregates chỉ là truy vấn, không ghi gì.

Số đếm giữ ở data/klaviyo_cache/message_daily/, mỗi ngày một file, giống Meta.
Key chỉ nằm trong header. Link phân trang của Klaviyo không chứa key nên đi theo link được.
"""

import json
import os
import sys
import time
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import dlt
import requests

from pipelines.dates import days, months, read_days, write_days
from pipelines.limits import Tracker

BASE = "https://a.klaviyo.com/api"
CACHE = Path(__file__).resolve().parent.parent.parent / "data" / "klaviyo_cache" / "message_daily"
TIMEZONE = "America/Phoenix"
# Bộ lọc datetime của Klaviyo hiểu theo UTC nếu không ghi múi giờ, còn nhóm theo ngày thì theo TIMEZONE.
# Thiếu offset thì mỗi khoảng mất 7 tiếng cuối của ngày cuối (lỗi tìm ra khi đối chiếu ngày 9/11).
PHOENIX_OFFSET = "-07:00"
# Tên metric chuẩn của Klaviyo → (tên cột ngắn, nhóm theo message nào)
METRICS = {
    "Received Email": ("received", "$message"),
    "Opened Email": ("opened", "$message"),
    "Clicked Email": ("clicked", "$message"),
    "Placed Order": ("placed_order", "$attributed_message"),
}
MAX_ATTEMPTS = 5
# metric-aggregates giới hạn khoảng 60 lần/phút; giãn 0,5 giây để không dồn
tracker = Tracker("klaviyo", min_interval=0.5)


def headers() -> dict:
    key = os.environ.get("KLAVIYO_PRIVATE_KEY", "").strip()
    revision = os.environ.get("KLAVIYO_API_REVISION", "").strip()
    if not key or not revision:
        sys.exit("Thiếu KLAVIYO_PRIVATE_KEY hoặc KLAVIYO_API_REVISION trong .env")
    return {"Authorization": f"Klaviyo-API-Key {key}", "revision": revision,
            "accept": "application/vnd.api+json", "content-type": "application/vnd.api+json"}


def call(method: str, url: str, **kwargs) -> dict:
    """Gọi Klaviyo, chờ rồi thử lại khi bị giới hạn tốc độ (429) hoặc lỗi máy chủ."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        tracker.call()
        response = requests.request(method, url, headers=headers(), timeout=120, **kwargs)
        if response.status_code == 200:
            return response.json()
        if response.status_code in (429, 500, 502, 503, 504) and attempt < MAX_ATTEMPTS:
            wait = int(response.headers.get("Retry-After", 10 * attempt))
            print(f"  Klaviyo bận (HTTP {response.status_code}), chờ {wait} giây")
            tracker.waited(wait)
            time.sleep(wait)
            continue
        try:
            errors = response.json().get("errors", [])
            detail = "; ".join(f"{e.get('title')}: {e.get('detail')}" for e in errors) or response.text[:300]
        except ValueError:
            detail = response.text[:300]
        path = url.replace(BASE, "").split("?")[0]
        sys.exit(f"Klaviyo trả HTTP {response.status_code} khi gọi {path}: {detail}")


def get_all(path: str, params: dict | None = None) -> tuple[list, list]:
    """GET có phân trang theo links.next. Trả (data, included)."""
    url, data, included = f"{BASE}{path}", [], []
    while url:
        page = call("GET", url, params=params)
        data.extend(page.get("data", []))
        included.extend(page.get("included", []))
        url, params = (page.get("links") or {}).get("next"), None
    return data, included


def fetch_campaigns() -> tuple[list, list]:
    """Revision mới để các trường trong attributes.definition; trạng thái và giờ gửi nằm ở message."""
    data, included = get_all("/campaigns", {"include": "campaign-messages"})
    campaigns, messages = [], {}
    for item in data:
        a = item["attributes"]
        d = a.get("definition") or {}
        send = d.get("send_settings") or {}
        campaigns.append({
            "campaign_id": item["id"], "name": d.get("name"), "builder": d.get("builder"),
            "archived": d.get("archived"), "send_strategy": send.get("send_strategy"),
            "send_timezone": send.get("send_timezone"),
            "created_at": a.get("created_at"), "updated_at": a.get("updated_at"),
        })
        for rel in ((item.get("relationships") or {}).get("campaign-messages") or {}).get("data", []):
            messages[rel["id"]] = {"message_id": rel["id"], "campaign_id": item["id"]}
    for inc in included:
        if inc.get("type") != "campaign-message" or inc["id"] not in messages:
            continue
        a = inc.get("attributes") or {}
        d = a.get("definition") or {}
        options = d.get("send_options") or {}
        messages[inc["id"]].update({
            "name": d.get("name"), "status": d.get("status"), "send_time": options.get("send_time"),
            "send_strategy": options.get("send_strategy"),
            "created_at": a.get("created"), "updated_at": a.get("updated"),
        })
    return campaigns, list(messages.values())


def fetch_flows() -> list[dict]:
    data, _ = get_all("/flows")
    return [{
        "flow_id": item["id"], "name": item["attributes"].get("name"),
        "status": item["attributes"].get("status"), "archived": item["attributes"].get("archived"),
        "trigger_type": item["attributes"].get("trigger_type"),
        "created_at": item["attributes"].get("created"), "updated_at": item["attributes"].get("updated"),
    } for item in data]


def field(attributes: dict, name: str):
    """Revision mới hay dời trường vào attributes.definition; đọc được cả hai chỗ."""
    return attributes.get(name, (attributes.get("definition") or {}).get(name))


FLOW_CACHE_HOURS = 24


def fetch_flow_messages(flows: list[dict]) -> list[dict]:
    """flow → flow-actions → flow-messages, để nối message_id trong message_daily về flow.

    Một message có thể nằm dưới nhiều action (A/B test: biến thể vừa thuộc bước A/B, vừa thuộc bước gửi),
    nên gộp theo message_id, giữ mọi action trong action_ids.
    """
    messages = {}
    for flow in flows:
        actions, _ = get_all(f"/flows/{flow['flow_id']}/flow-actions")
        for action in actions:
            data, _ = get_all(f"/flow-actions/{action['id']}/flow-messages")
            for item in data:
                a = item.get("attributes") or {}
                row = messages.setdefault(item["id"], {
                    "message_id": item["id"], "flow_id": flow["flow_id"], "action_ids": [],
                    "name": field(a, "name"), "channel": field(a, "channel"),
                    "created_at": field(a, "created"), "updated_at": field(a, "updated"),
                })
                if action["id"] not in row["action_ids"]:
                    row["action_ids"].append(action["id"])
    for row in messages.values():
        row["action_ids"] = ",".join(sorted(row["action_ids"]))
    return list(messages.values())


def flow_messages_with_cache(flows: list[dict], cache_file: Path) -> list[dict]:
    """Đi hết 11 flow tốn khoảng 90 lần gọi, nên giữ kết quả 24 giờ."""
    if cache_file.is_file():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if time.time() - cached["fetched_at"] < FLOW_CACHE_HOURS * 3600:
            print(f"  flow messages: dùng cache ({len(cached['messages'])} message)")
            return cached["messages"]
    messages = fetch_flow_messages(flows)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps({"fetched_at": time.time(), "messages": messages}, ensure_ascii=False),
                          encoding="utf-8")
    return messages


def fetch_metrics() -> list[dict]:
    data, _ = get_all("/metrics")
    return [{
        "metric_id": item["id"], "name": item["attributes"].get("name"),
        "integration": ((item["attributes"].get("integration") or {}).get("name")),
    } for item in data]


def aggregate(metric_id: str, by: str, start: date, end: date, with_value: bool) -> tuple[list, list]:
    """Đếm theo ngày Phoenix và theo message. Trả (các ngày, các nhóm)."""
    measurements = ["count", "sum_value"] if with_value else ["count"]
    body = {"data": {"type": "metric-aggregate", "attributes": {
        "metric_id": metric_id, "measurements": measurements, "interval": "day", "by": [by],
        "page_size": 500, "timezone": TIMEZONE,
        "filter": [f"greater-or-equal(datetime,{start}T00:00:00{PHOENIX_OFFSET})",
                   f"less-than(datetime,{end + timedelta(days=1)}T00:00:00{PHOENIX_OFFSET})"],
    }}}
    result = call("POST", f"{BASE}/metric-aggregates", data=json.dumps(body))["data"]["attributes"]
    return result.get("dates", []), result.get("data", [])


def fetch_message_daily(metrics: list[dict], since: date, until: date, cache: Path = CACHE) -> int:
    """Gọi Klaviyo cho [since, until] theo từng tháng, ghi đè cache của từng ngày."""
    ids = {}
    for metric in metrics:
        if metric["name"] in METRICS and metric["name"] not in ids:
            ids[metric["name"]] = metric["metric_id"]
    missing = sorted(set(METRICS) - set(ids))
    if missing:
        print(f"  Cảnh báo: tài khoản không có metric {', '.join(missing)}")
    total = 0
    for start, end in months(since, until):
        by_day = {day: [] for day in days(start, end)}
        for name, metric_id in ids.items():
            short, by = METRICS[name]
            dates, groups = aggregate(metric_id, by, start, end, with_value=short == "placed_order")
            for group in groups:
                message_id = (group.get("dimensions") or [None])[0]
                counts = group["measurements"].get("count", [])
                values = group["measurements"].get("sum_value", [None] * len(counts))
                for stamp, count, value in zip(dates, counts, values):
                    day = stamp[:10]
                    if day in by_day and (count or value):
                        by_day[day].append({"date": day, "metric": short, "message_id": message_id or None,
                                            "count": count, "value": value})
        write_days(cache, by_day)
        rows = sum(len(r) for r in by_day.values())
        total += rows
        print(f"  {start} đến {end}: {rows:,} dòng ngày × message × metric")
    return total


def cached_message_daily(cache: Path = CACHE):
    for row in read_days(cache):
        yield {
            "date": date.fromisoformat(row["date"]),
            "metric": row["metric"],
            # Message rỗng: event không gắn với email nào (ví dụ đơn không do Klaviyo mang lại)
            "message_id": row.get("message_id") or "(none)",
            "count": int(row["count"]) if row.get("count") is not None else 0,
            # Klaviyo trả tổng tiền dạng float (7260.470000000001); làm tròn về xu cho NUMERIC
            "value": round(Decimal(str(row["value"])), 2) if row.get("value") is not None else None,
        }


@dlt.source(name="klaviyo", max_table_nesting=0)
def klaviyo(since: date, until: date, cache: Path = CACHE):
    print("== Klaviyo: campaigns, flows, metrics ==")
    campaigns, messages = fetch_campaigns()
    flows = fetch_flows()
    flow_messages = flow_messages_with_cache(flows, cache.parent / "flow_messages.json")
    metrics = fetch_metrics()
    print(f"  {len(campaigns):,} campaign, {len(messages):,} campaign message, {len(flows):,} flow, "
          f"{len(metrics):,} metric, {len(flow_messages):,} flow message")
    print(f"== Klaviyo: đếm theo ngày × message, {since} đến {until} ==")
    fetch_message_daily(metrics, since, until, cache)
    tracker.save(since=since, until=until)

    yield dlt.resource(campaigns, name="campaigns", primary_key="campaign_id")
    yield dlt.resource(messages, name="campaign_messages", primary_key="message_id")
    yield dlt.resource(flows, name="flows", primary_key="flow_id")
    yield dlt.resource(flow_messages, name="flow_messages", primary_key="message_id")
    yield dlt.resource(metrics, name="metrics", primary_key="metric_id")
    yield dlt.resource(cached_message_daily(cache), name="message_daily",
                       primary_key=["date", "metric", "message_id"])
