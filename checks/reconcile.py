"""Đối chiếu tầng raw với số đếm do chính nguồn trả, không so tay.

- Shopify: ordersCount theo từng tháng (cùng bộ lọc ngày như Admin) so với raw.shopify_orders.
- Meta: spend cấp tài khoản theo ngày (1 lần gọi mỗi tháng) so với tổng spend cấp ad.
- Klaviyo: tổng Placed Order theo ngày (không nhóm theo message) so với tổng các message trong raw.

Chỉ so khoảng vừa nạp, để không hỏi lại nguồn những tháng đã khớp (Meta dùng chung quota với đội ads):
- mặc định: 7 ngày đã trọn gần nhất theo Phoenix (đúng khoảng lần chạy hằng ngày lấy);
- --since/--until: đúng khoảng vừa nạp lịch sử;
- --all: cả kho (tốn nhiều lần gọi, chỉ dùng khi cần chứng minh toàn bộ, ví dụ trước buổi demo).

Dùng token Shopify, Meta, Klaviyo (ít lần gọi, Meta vẫn qua bộ giữ quota) và khoá GCP.
Chạy từ thư mục gốc:  python checks/reconcile.py [--only meta klaviyo] [--since 2026-03-01 --until 2026-03-31 | --all]
Thoát mã 1 nếu có chỗ lệch.
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

MONEY_TOLERANCE = Decimal("0.01")  # lệch tối đa 1% theo cổng khớp số của brief; ở raw đòi gần như bằng
# Meta: tổng spend cấp ad vốn thấp hơn cấp tài khoản vài chục xu mỗi ngày (làm tròn từng ad, phần không gán
# cho ad nào). Chẩn đoán 9/11: 8/10 thiếu 0,34, 23/10 thiếu 0,53, ngay tại Meta. Cho phép tối đa 1 USD/ngày.
META_DAILY_ABS = Decimal("1.00")


def compare(source: dict, warehouse: dict, tolerance: Decimal = Decimal("0"),
            absolute: Decimal = Decimal("0")) -> list[tuple]:
    """Trả các khoá lệch: (khoá, số nguồn, số kho). Lệch khi vượt cả ngưỡng tương đối lẫn ngưỡng tuyệt đối."""
    gaps = []
    for key in sorted(set(source) | set(warehouse)):
        a, b = Decimal(str(source.get(key, 0))), Decimal(str(warehouse.get(key, 0)))
        base = max(abs(a), abs(b))
        if base and abs(a - b) / base > tolerance and abs(a - b) > absolute:
            gaps.append((key, a, b))
    return gaps


RESULTS = {}  # nguồn → kết quả lần chạy này, ghi ra logs/reconcile.json cho trang demo


def report(title: str, source: dict, warehouse: dict, tolerance: Decimal = Decimal("0"),
           absolute: Decimal = Decimal("0"), name: str = "") -> bool:
    gaps = compare(source, warehouse, tolerance, absolute)
    total_a, total_b = sum(Decimal(str(v)) for v in source.values()), sum(Decimal(str(v)) for v in warehouse.values())
    if name:
        RESULTS[name] = {"title": title, "ok": not gaps, "source": str(total_a), "warehouse": str(total_b),
                         "periods": len(source), "gaps": [[k, str(a), str(b)] for k, a, b in gaps]}
    print(f"  {'✓' if not gaps else '✗'} {title}: nguồn {total_a:,}, kho {total_b:,}, lệch {len(gaps)}/{len(source)} kỳ")
    for key, a, b in gaps[:15]:
        print(f"      {key}: nguồn {a:,}, kho {b:,} (chênh {b - a:+,})")
    return not gaps


def save_results() -> None:
    """Giữ kết quả mới nhất của từng nguồn (nguồn không chạy lần này thì giữ kết quả cũ)."""
    import os
    from datetime import datetime, timezone

    logs = Path(os.environ.get("DATAE_LOGS") or ROOT / "logs")
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / "reconcile.json"
    saved = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    saved.update({name: {**result, "at": at} for name, result in RESULTS.items()})
    path.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")


def bq_rows(sql: str) -> dict:
    from google.cloud import bigquery

    from pipelines.bq import client

    bq = client()
    job = bq.query(sql.replace("{p}", bq.project),
                   job_config=bigquery.QueryJobConfig(maximum_bytes_billed=200 * 1024 * 1024))
    return {str(r[0]): r[1] for r in job.result()}


def month_starts(first: date, last: date):
    start = first.replace(day=1)
    while start <= last:
        following = (start + timedelta(days=32)).replace(day=1)
        yield start, following
        start = following


def span(args, done: date) -> tuple[date, date] | None:
    """Khoảng cần so. None = cả kho."""
    if args.all:
        if args.since or args.until:
            sys.exit("Dùng --all hoặc --since/--until, không dùng cả hai.")
        return None
    until = args.until or done
    since = args.since or (until - timedelta(days=6))
    if since > until:
        sys.exit(f"--since {since} sau --until {until}.")
    return since, until


def between(column: str, window: tuple[date, date] | None) -> str:
    return f"where {column} between '{window[0]}' and '{window[1]}'" if window else ""


def warehouse_span(table: str) -> tuple[date, date]:
    first, last = bq_rows("select 'x', concat(cast(min(date) as string), ',', cast(max(date) as string)) "
                          f"from `{{p}}.raw.{table}`")["x"].split(",")
    return date.fromisoformat(first), date.fromisoformat(last)


def phoenix_range(start: date, following: date, cutoff: str | None = None) -> str:
    """Bộ lọc tìm kiếm Shopify theo mốc giờ đầy đủ.

    Ghi chỉ ngày (created_at:<2026-11-01) thì Shopify tính luôn cả ngày 1/11, nên mỗi tháng bị đếm dư
    ngày đầu của tháng sau (lệch 406 đơn khi đối chiếu ngày 9/11).
    """
    upper = f"{following}T00:00:00-07:00"
    if cutoff and cutoff < datetime.fromisoformat(upper).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"):
        upper = cutoff  # tháng đang chạy: chỉ đếm tới đơn mới nhất kho đã có
    return f"created_at:>='{start}T00:00:00-07:00' created_at:<'{upper}'"


def check_shopify(window: tuple[date, date] | None = None) -> bool:
    from pipelines.sources.shopify import graphql

    print("\n== Shopify: ordersCount theo tháng ==")
    timezone = graphql("{ shop { ianaTimezone } }")["shop"]["ianaTimezone"]
    print(f"  Múi giờ shop: {timezone} (Shopify lọc ngày theo múi giờ này)")
    local = f"date(created_at, '{timezone}')"
    warehouse = bq_rows(f"""select format_date('%Y-%m', {local}), count(*)
                            from `{{p}}.raw.shopify_orders` {between(local, window)} group by 1""")
    # Đơn tạo sau lần nạp gần nhất thì kho chưa thể có; chỉ so tới đơn mới nhất kho đã biết (+1 giây)
    latest = bq_rows("select 'x', format_timestamp('%Y-%m-%dT%H:%M:%SZ', "
                     "timestamp_add(max(created_at), interval 1 second)) from `{p}.raw.shopify_orders`")["x"]
    print(f"  So tới đơn mới nhất trong kho: {latest}")
    first, last = window or (date(2024, 11, 1), date.today())
    source = {}
    for start, following in month_starts(first, last):
        lower, upper = max(start, first), min(following, last + timedelta(days=1))
        data = graphql('query($q: String!) { ordersCount(query: $q) { count precision } }',
                       {"q": phoenix_range(lower, upper, latest)})["ordersCount"]
        if data["precision"] != "EXACT":
            print(f"  Cảnh báo: {start:%Y-%m} Shopify chỉ trả số gần đúng ({data['precision']})")
        if data["count"]:
            source[f"{start:%Y-%m}"] = data["count"]
    return report(f"Số đơn theo tháng ({first} đến {last})", source, warehouse, name="shopify")


def check_meta(window: tuple[date, date] | None = None) -> bool:
    from pipelines.sources import meta

    print("\n== Meta: spend cấp tài khoản theo ngày ==")
    first, last = window or warehouse_span("meta_ad_insights_daily")
    accounts, active = meta.ad_accounts(first, last)
    source = {}
    for account in active:
        for start, following in month_starts(first, last):
            end = min(following - timedelta(days=1), last)
            rows = meta.get_all(f"act_{account['account_id']}/insights", {
                "level": "account", "time_increment": 1, "fields": "spend",
                "time_range": json.dumps({"since": str(max(start, first)), "until": str(end)}), "limit": 100,
            })
            for row in rows:
                key = f"{account['account_id']} {row['date_start']}"
                source[key] = Decimal(row["spend"])
    warehouse = bq_rows("""select concat(ad_account_id, ' ', cast(date as string)), sum(spend)
                           from `{p}.raw.meta_ad_insights_daily` """ + between("date", (first, last)) + " group by 1")
    meta.tracker.save(check="reconcile")
    return report(f"Spend theo ngày ({first} đến {last}, cho phép ≤ {META_DAILY_ABS} USD/ngày)", source, warehouse,
                  MONEY_TOLERANCE / 100, META_DAILY_ABS, name="meta")


def check_klaviyo(window: tuple[date, date] | None = None) -> bool:
    from pipelines.sources import klaviyo

    print("\n== Klaviyo: tổng Placed Order theo ngày ==")
    first, last = window or warehouse_span("klaviyo_message_daily")
    metric_id = next(m["metric_id"] for m in klaviyo.fetch_metrics() if m["name"] == "Placed Order")
    source = {}
    for start, following in month_starts(first, last):
        end = min(following - timedelta(days=1), last)
        body = {"data": {"type": "metric-aggregate", "attributes": {
            "metric_id": metric_id, "measurements": ["count"], "interval": "day", "timezone": klaviyo.TIMEZONE,
            "filter": [f"greater-or-equal(datetime,{max(start, first)}T00:00:00{klaviyo.PHOENIX_OFFSET})",
                       f"less-than(datetime,{end + timedelta(days=1)}T00:00:00{klaviyo.PHOENIX_OFFSET})"]}}}
        result = klaviyo.call("POST", f"{klaviyo.BASE}/metric-aggregates", data=json.dumps(body))["data"]["attributes"]
        for group in result.get("data", []):
            for stamp, count in zip(result["dates"], group["measurements"]["count"]):
                if count:
                    source[stamp[:10]] = source.get(stamp[:10], 0) + count
    warehouse = bq_rows("""select cast(date as string), sum(count) from `{p}.raw.klaviyo_message_daily` """
                        + between("date", (first, last)) + " and metric = 'placed_order' group by 1")
    return report(f"Placed Order theo ngày ({first} đến {last})", source, warehouse, name="klaviyo")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="*", default=["shopify", "meta", "klaviyo"], choices=["shopify", "meta", "klaviyo"])
    parser.add_argument("--since", type=date.fromisoformat)
    parser.add_argument("--until", type=date.fromisoformat)
    parser.add_argument("--all", action="store_true", help="so cả kho (tốn nhiều lần gọi)")
    args = parser.parse_args()
    from pipelines.dates import last_complete_day
    window = span(args, last_complete_day())
    print("Khoảng so: " + ("cả kho" if window is None else f"{window[0]} đến {window[1]}"))
    checks = {"shopify": check_shopify, "meta": check_meta, "klaviyo": check_klaviyo}
    results = [checks[name](window) for name in args.only]
    save_results()
    print()
    if all(results):
        print("OK: raw khớp số đếm của nguồn")
    else:
        print("CÓ LỆCH: xem các kỳ ✗ ở trên")
        sys.exit(1)
