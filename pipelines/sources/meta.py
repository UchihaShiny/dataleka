"""Nguồn dlt cho Meta Ads: insights theo ad × ngày và cây campaign/adset/ad. Chỉ đọc (ads_read).

Kho chạy Sandbox nên mỗi lần nạp phải ghi đè cả bảng. Để không phải kéo lại 13 tháng mỗi ngày
(quota Meta dùng chung với bên vận hành ads), số đã lấy được giữ ở data/meta_cache/insights/,
mỗi ngày một file. Mỗi lần chạy chỉ gọi Meta cho khoảng ngày yêu cầu, ghi đè file của các ngày đó,
rồi nạp toàn bộ cache vào BigQuery.

Không dùng tham số ?ids= vì Meta bỏ từ v26. Token chỉ nằm trong header.

Giới hạn (app ở Dev tier): điểm cả app tối đa 60, mỗi lần đọc 1 điểm, hồi sau 300 giây; chạm trần thì
cả app bị chặn 300 giây, kể cả đội ads nếu dùng chung app. Vì vậy:
- giãn tối thiểu 15 giây giữa 2 lần gọi (≤ 20 lần/5 phút);
- đọc header mức dùng sau mỗi lần gọi: ≥ 50% thì chờ, ≥ 75% thì dừng hẳn;
- chỉ gọi insights cho tài khoản có spend trong khoảng ngày; cây ad lấy lại khi cache cũ hơn 24 giờ.
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

from pipelines.dates import read_days, weeks, write_days
from pipelines.limits import Tracker

CACHE = Path(__file__).resolve().parent.parent.parent / "data" / "meta_cache" / "insights"
ADS_CACHE_HOURS = 24
# Token dùng chung app với đội ads (anh Quang xác nhận 2026-11-09): luôn chừa ít nhất 25% quota cho họ
MIN_INTERVAL = 15  # giây giữa 2 lần gọi
WAIT_AT, STOP_AT = 50, 75  # % mức dùng
USAGE_HEADERS = ["x-business-use-case-usage", "x-ad-account-usage", "x-fb-ads-insights-throttle", "x-app-usage"]
tracker = Tracker("meta", MIN_INTERVAL)
INSIGHT_FIELDS = [
    "account_id", "campaign_id", "campaign_name", "adset_id", "adset_name", "ad_id", "ad_name",
    "spend", "impressions", "reach", "clicks", "inline_link_clicks", "actions", "action_values",
]
AD_FIELDS = (
    "id,name,created_time,updated_time,effective_status,"
    "adset{id,name},campaign{id,name,objective},creative{id}"
)
RATE_LIMIT_CODES = {17, 32, 613, 80000, 80004}
# Mã 4: cả app (dùng chung với đội ads) chạm giới hạn. Thử lại chỉ ăn thêm vào phần của đội ads, nên dừng hẳn.
# (10/11/2026: reconcile so lại cả kho sau mỗi tháng nạp, tổng 154 lần gọi trong ngày, gặp mã 4.)
APP_LIMIT_CODES = {4}
# Lỗi tạm phía Meta (mã 1 "unknown", mã 2 "service temporarily unavailable"), có khi trả HTTP 400
TRANSIENT_CODES = {1, 2}
MAX_ATTEMPTS = 5


class MetaError(SystemExit):
    """Meta trả lỗi không thử lại được. Vẫn là SystemExit (pipeline dừng như cũ), kèm `error` để đọc mã."""

    def __init__(self, message: str, error: dict):
        super().__init__(message)
        self.error = error


def settings() -> tuple[str, str]:
    token = os.environ.get("META_ACCESS_TOKEN", "").strip()
    version = os.environ.get("META_API_VERSION", "").strip()
    if not token or not version:
        sys.exit("Thiếu META_ACCESS_TOKEN hoặc META_API_VERSION trong .env")
    return token, version


def usage(headers) -> tuple[float, float]:
    """Đọc mọi header mức dùng của Meta. Trả (phần trăm cao nhất, số giây Meta bảo chờ)."""
    peak, regain = 0.0, 0.0

    def walk(value):
        nonlocal peak, regain
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "estimated_time_to_regain_access" and isinstance(item, (int, float)):
                    regain = max(regain, item * 60)  # Meta tính bằng phút
                elif key == "reset_time_duration" and isinstance(item, (int, float)):
                    regain = max(regain, float(item))
                elif isinstance(item, (int, float)) and not isinstance(item, bool) and (
                        key.endswith("_pct") or key in ("call_count", "total_cputime", "total_time")):
                    peak = max(peak, float(item))
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for name in USAGE_HEADERS:
        raw = headers.get(name)
        if raw:
            try:
                walk(json.loads(raw))
            except ValueError:
                pass
    return peak, regain


def respect(headers, path: str) -> None:
    """Chờ hoặc dừng theo mức dùng Meta vừa báo, trước khi gọi tiếp."""
    peak, regain = usage(headers)
    tracker.seen(peak)
    if peak >= STOP_AT:
        tracker.save(stopped=f"{peak:.0f}% khi gọi {path}")
        sys.exit(f"Meta báo mức dùng {peak:.0f}% (ngưỡng dừng {STOP_AT}%). Dừng để giữ quota cho đội ads, "
                 "chưa ghi gì vào BigQuery. Chạy lại sau 1 giờ.")
    if peak >= WAIT_AT:
        wait = max(regain, 60)
        print(f"  Meta báo mức dùng {peak:.0f}%, chờ {wait:.0f} giây cho quota hồi")
        tracker.waited(wait)
        time.sleep(wait)


def get(path: str, params: dict) -> dict:
    """GET Graph API: giãn nhịp, đọc mức dùng, thử lại khi bị giới hạn tốc độ hoặc lỗi máy chủ."""
    token, version = settings()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        tracker.call()
        response = requests.get(
            f"https://graph.facebook.com/{version}/{path}", params=params,
            headers={"Authorization": f"Bearer {token}"}, timeout=120,
        )
        body = response.json()
        respect(response.headers, path)
        if response.status_code == 200:
            return body
        error = body.get("error", {})
        if error.get("code") in APP_LIMIT_CODES | RATE_LIMIT_CODES:
            # Ghi nguyên header mức dùng lúc bị chặn, để biết con số nào chạm 100% (10/11 chỉ đoán được)
            tracker.event(code=error.get("code"), subcode=error.get("error_subcode"), path=path,
                          message=(error.get("message") or "")[:200],
                          headers={name: response.headers.get(name) for name in USAGE_HEADERS
                                   if response.headers.get(name)})
        if error.get("code") in APP_LIMIT_CODES:
            tracker.save(stopped=f"mã {error.get('code')} (giới hạn cả app) khi gọi {path}")
            raise MetaError(f"Meta báo cả app chạm giới hạn (mã {error.get('code')}), app dùng chung với đội ads. "
                            "Dừng hẳn, chưa ghi gì vào BigQuery. Không gọi Meta ít nhất 1 giờ và báo anh Quang.", error)
        transient = response.status_code >= 500 or error.get("code") in TRANSIENT_CODES or error.get("is_transient")
        if (transient or error.get("code") in RATE_LIMIT_CODES) and attempt < MAX_ATTEMPTS:
            wait = 300 if error.get("code") in RATE_LIMIT_CODES else 30 * attempt  # bị chặn thì chờ hết 300 giây
            print(f"  Meta bận (mã {error.get('code')}), chờ {wait} giây rồi thử lại")
            tracker.waited(wait)
            time.sleep(wait)
            continue
        detail = " | ".join(str(error[k]) for k in ("error_subcode", "error_user_title", "error_user_msg") if error.get(k))
        raise MetaError(f"Meta trả HTTP {response.status_code}, mã {error.get('code')}: {error.get('message')}"
                        + (f" ({detail})" if detail else "") + f"\n  khi gọi {path}", error)


def get_all(path: str, params: dict) -> list[dict]:
    """Lấy hết các trang bằng con trỏ after (link next có token trong URL nên không dùng)."""
    params, rows = dict(params), []
    while True:
        page = get(path, params)
        rows.extend(page.get("data", []))
        if "next" not in page.get("paging", {}):
            return rows
        params["after"] = page["paging"]["cursors"]["after"]


def ad_accounts(since: date, until: date) -> tuple[list[dict], list[dict]]:
    """Một lần gọi: mọi tài khoản kèm spend của khoảng ngày. Trả (tất cả, tài khoản có spend)."""
    span = json.dumps({"since": str(since), "until": str(until)})
    accounts = get_all("me/adaccounts", {
        "fields": f"account_id,name,currency,timezone_name,insights.time_range({span}){{spend}}", "limit": 100,
    })
    active = [a for a in accounts
              if any(Decimal(i.get("spend") or 0) > 0 for i in (a.get("insights") or {}).get("data", []))]
    return accounts, active


def to_decimal(value):
    return Decimal(value) if value not in (None, "") else None


def to_int(value):
    return int(value) if value not in (None, "") else None


def fetch_insights(accounts: list[dict], since: date, until: date, cache: Path = CACHE) -> int:
    """Gọi Meta cho [since, until], ghi đè file cache của từng ngày. Trả số dòng đã lấy.

    Mỗi lần gọi tối đa 7 ngày: cả tháng × cấp ad × từng ngày quá nặng, Meta trả mã 1/2 (tháng 5/2026)."""
    total = 0
    for start, end in weeks(since, until):
        by_day = {(start + timedelta(days=i)).isoformat(): [] for i in range((end - start).days + 1)}
        for account in accounts:
            rows = get_all(f"act_{account['account_id']}/insights", {
                "level": "ad", "time_increment": 1, "limit": 500,
                "time_range": json.dumps({"since": str(start), "until": str(end)}),
                "fields": ",".join(INSIGHT_FIELDS),
            })
            for row in rows:
                by_day[row["date_start"]].append({
                    "ad_account_id": account["account_id"],
                    "account_currency": account.get("currency"),
                    "account_timezone": account.get("timezone_name"),
                    **row,
                })
        write_days(cache, by_day)
        total += sum(len(rows) for rows in by_day.values())
        print(f"  {start} đến {end}: {sum(len(r) for r in by_day.values()):,} dòng ad × ngày")
    return total


def cached_insights(cache: Path = CACHE):
    for row in read_days(cache):
        yield {
            "ad_account_id": row["ad_account_id"],
            "account_currency": row.get("account_currency"),
            "account_timezone": row.get("account_timezone"),
            "date": date.fromisoformat(row["date_start"]),
            "campaign_id": row.get("campaign_id"),
            "campaign_name": row.get("campaign_name"),
            "adset_id": row.get("adset_id"),
            "adset_name": row.get("adset_name"),
            "ad_id": row["ad_id"],
            "ad_name": row.get("ad_name"),
            "spend": to_decimal(row.get("spend")),
            "impressions": to_int(row.get("impressions")),
            "reach": to_int(row.get("reach")),
            "clicks": to_int(row.get("clicks")),
            "inline_link_clicks": to_int(row.get("inline_link_clicks")),
            # Giữ nguyên JSON; tầng silver chọn đúng action_type (purchase, không cộng omni_purchase)
            "actions": row.get("actions"),
            "action_values": row.get("action_values"),
        }


def ads_with_cache(accounts: list[dict], cache_file: Path) -> list[dict]:
    """Cây ad theo từng tài khoản, chỉ gọi Meta cho tài khoản có cache cũ hơn 24 giờ."""
    cached = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.is_file() else {}
    now = time.time()
    stale = [a for a in accounts
             if now - cached.get(a["account_id"], {}).get("fetched_at", 0) > ADS_CACHE_HOURS * 3600]
    for account in stale:
        cached[account["account_id"]] = {"fetched_at": now, "ads": fetch_ads([account])}
    if stale:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(cached, ensure_ascii=False), encoding="utf-8")
    print(f"  cây ad: gọi Meta cho {len(stale)} tài khoản, dùng cache cho {len(accounts) - len(stale)}")
    return [ad for entry in cached.values() for ad in entry["ads"]]


def fetch_ads(accounts: list[dict]) -> list[dict]:
    """Thông tin thêm của từng ad: ngày tạo, trạng thái, objective, creative.

    Không truyền effective_status: Meta v27 trả 400 Invalid parameter với danh sách trạng thái.
    Ad đã xoá có thể không có ở đây, nhưng tên và id campaign/adset/ad của nó vẫn nằm trong insights.
    """
    ads = []
    for account in accounts:
        rows = get_all(f"act_{account['account_id']}/ads", {
            "fields": AD_FIELDS, "limit": 500,
        })
        for row in rows:
            ads.append({
                "ad_id": row["id"],
                "ad_account_id": account["account_id"],
                "ad_name": row.get("name"),
                "created_time": row.get("created_time"),
                "updated_time": row.get("updated_time"),
                "effective_status": row.get("effective_status"),
                "adset_id": (row.get("adset") or {}).get("id"),
                "adset_name": (row.get("adset") or {}).get("name"),
                "campaign_id": (row.get("campaign") or {}).get("id"),
                "campaign_name": (row.get("campaign") or {}).get("name"),
                "campaign_objective": (row.get("campaign") or {}).get("objective"),
                "creative_id": (row.get("creative") or {}).get("id"),
            })
        print(f"  {account.get('name')}: {len(rows):,} ad")
    return ads


@dlt.source(name="meta", max_table_nesting=0)
def meta(since: date, until: date, cache: Path = CACHE):
    accounts, active = ad_accounts(since, until)
    print(f"== Meta: {len(accounts)} tài khoản, {len(active)} có spend; insights {since} đến {until} ==")
    fetch_insights(active, since, until, cache)
    print("== Meta: cây campaign/adset/ad ==")
    ads = ads_with_cache(active, cache.parent / "ads.json")
    tracker.save(since=since, until=until)

    yield dlt.resource(
        cached_insights(cache), name="ad_insights_daily", primary_key=["ad_account_id", "date", "ad_id"],
        columns={"actions": {"data_type": "json"}, "action_values": {"data_type": "json"}},
    )
    yield dlt.resource(ads, name="ads", primary_key="ad_id")
