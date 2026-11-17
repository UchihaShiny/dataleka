"""Khám phá schema Meta trên 1 ngày mẫu, trước khi pull lịch sử. Chỉ đọc, không ghi BigQuery.

Bước 1, Meta tự mô tả: `GET /{id}?metadata=1` trên một campaign, adset, ad, creative có thật → danh sách mọi
trường (tên, kiểu, mô tả). Lưu ở data/explore/meta/_schema_<loại>.json.
Bước 2, mẫu thật: mọi campaign/adset/ad/creative có spend trong ngày (id lấy từ cache insights đã nạp),
xin đủ mọi trường ở bước 1; insights 1 ngày với bộ trường rộng; insights theo vị trí hiển thị (breakdown).
Trường nào Meta từ chối (không tồn tại, cần quyền khác) thì bỏ, ghi lý do vào _dropped.json, gọi lại.

Đi qua meta.get nên vẫn giãn 15 giây, đọc mức dùng, ≥ 50% chờ, ≥ 75% dừng. Khoảng 20–30 lần gọi.
Chạy từ thư mục gốc (ngoài giờ làm việc Phoenix):  python checks/explore_meta.py [--day 2026-11-07]
Sau đó:  python checks/profile_sample.py meta
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "checks"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from pipelines.dates import guard_work_hours  # noqa: E402
from pipelines.sources import meta  # noqa: E402
from profile_sample import save  # noqa: E402

CACHE = ROOT / "data" / "meta_cache"
CHUNK = 50
# Dùng khi Meta không trả metadata: bộ trường rộng theo Marketing API reference
FALLBACK = {
    "campaign": "id,name,account_id,objective,status,configured_status,effective_status,buying_type,bid_strategy,"
                "daily_budget,lifetime_budget,budget_remaining,spend_cap,special_ad_categories,smart_promotion_type,"
                "start_time,stop_time,created_time,updated_time",
    "adset": "id,name,account_id,campaign_id,status,effective_status,optimization_goal,billing_event,bid_strategy,"
             "bid_amount,daily_budget,lifetime_budget,targeting,promoted_object,attribution_spec,destination_type,"
             "learning_stage_info,start_time,end_time,created_time,updated_time",
    "ad": "id,name,account_id,campaign_id,adset_id,status,configured_status,effective_status,creative,"
          "tracking_specs,conversion_specs,ad_review_feedback,issues_info,created_time,updated_time",
    "adcreative": "id,name,title,body,status,object_type,call_to_action_type,link_url,url_tags,image_hash,image_url,"
                  "thumbnail_url,video_id,object_story_spec,asset_feed_spec,effective_object_story_id,"
                  "instagram_permalink_url,product_set_id,degrees_of_freedom_spec",
}
INSIGHTS_WIDE = (
    "date_start,date_stop,account_currency,campaign_id,adset_id,ad_id,objective,optimization_goal,buying_type,"
    "attribution_setting,spend,impressions,reach,frequency,cpm,cpc,ctr,cpp,clicks,unique_clicks,unique_ctr,"
    "inline_link_clicks,inline_link_click_ctr,outbound_clicks,outbound_clicks_ctr,actions,action_values,"
    "cost_per_action_type,purchase_roas,website_purchase_roas,conversions,conversion_values,"
    "video_play_actions,video_p25_watched_actions,video_p50_watched_actions,video_p75_watched_actions,"
    "video_p100_watched_actions,video_thruplay_watched_actions,video_avg_time_watched_actions,"
    "quality_ranking,engagement_rate_ranking,conversion_rate_ranking"
).split(",")
EDGES = [("campaign", "campaigns"), ("adset", "adsets"), ("ad", "ads"), ("adcreative", "adcreatives")]


def bad_field(message: str, fields: list[str]) -> str | None:
    """Tìm trường Meta vừa từ chối trong câu báo lỗi, ví dụ 'nonexisting field (foo) on node type'."""
    for name in re.findall(r"\(([A-Za-z_][\w.]*)\)", message):
        if name in fields and name != "id":
            return name
    if "field" in message.lower():
        for name in sorted(fields, key=len, reverse=True):
            if name != "id" and re.search(rf"(?<![\w.]){re.escape(name)}(?![\w.])", message):
                return name
    return None


def adaptive(fetch, fields: list[str], dropped: list, label: str):
    """Gọi fetch(fields); trường nào bị từ chối thì bỏ và gọi lại (tối đa 15 lần mỗi loại, để giữ quota)."""
    fields = list(fields)
    for _ in range(15):
        try:
            return fetch(fields), fields
        except meta.MetaError as error:
            message = error.error.get("message", "") or str(error.code)
            name = bad_field(message, fields)
            if not name:
                raise
            fields.remove(name)
            dropped.append({"where": label, "field": name, "reason": message[:200]})
            print(f"  {label}: Meta từ chối trường {name}, bỏ rồi gọi lại")
    sys.exit(f"{label}: bỏ 15 trường vẫn lỗi, dừng để giữ quota. Dán log cho mình.")


def schema(kind: str, node_id: str) -> list[str]:
    """Bước 1: Meta tự mô tả node."""
    body = meta.get(node_id, {"metadata": 1, "fields": "id"})
    described = body.get("metadata") or {}
    save("meta", f"_schema_{kind}", described)
    names = [f["name"] for f in described.get("fields", []) if f.get("name")]
    if names:
        print(f"  {kind}: Meta mô tả {len(names)} trường, {len(described.get('connections') or {})} connection")
        return names
    print(f"  {kind}: Meta không trả metadata, dùng bộ trường rộng theo tài liệu")
    return FALLBACK[kind].split(",")


def by_ids(account: str, edge: str, ids: list[str], fields: list[str], dropped: list, kind: str) -> list[dict]:
    """Bước 2: lấy đủ trường cho đúng các id có spend trong ngày, mỗi lần 50 id."""
    rows = []
    for start in range(0, len(ids), CHUNK):
        chunk = ids[start:start + CHUNK]

        def fetch(names, chunk=chunk):
            return meta.get_all(f"act_{account}/{edge}", {
                "fields": ",".join(names), "limit": 100,
                "filtering": json.dumps([{"field": "id", "operator": "IN", "value": chunk}]),
            })
        try:
            got, fields = adaptive(fetch, fields, dropped, kind)
        except meta.MetaError as error:  # edge không nhận lọc theo id: lấy lẻ tối đa 20 node
            print(f"  {kind}: lọc theo id bị từ chối ({error.error.get('message', '')[:80]}), lấy lẻ 20 node")
            got = []
            for node_id in ids[:20]:
                row, fields = adaptive(lambda names, n=node_id: meta.get(n, {"fields": ",".join(names)}),
                                       fields, dropped, kind)
                got.append(row)
            rows.extend(got)
            break
        rows.extend(got)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", type=date.fromisoformat, default=date(2026, 11, 7))
    parser.add_argument("--force", action="store_true", help="chạy cả trong giờ làm việc Phoenix (đã báo anh)")
    args = parser.parse_args()
    guard_work_hours(args.force)

    day_file = CACHE / "insights" / f"{args.day}.json"
    if not day_file.is_file():
        sys.exit(f"Chưa có cache insights ngày {args.day}. Nạp ngày đó bằng pipelines.run trước.")
    insights = json.loads(day_file.read_text(encoding="utf-8"))
    ads_cache = json.loads((CACHE / "ads.json").read_text(encoding="utf-8")) if (CACHE / "ads.json").is_file() else {}
    creative_of = {ad["ad_id"]: ad.get("creative_id") for entry in ads_cache.values() for ad in entry["ads"]}

    ids = {
        "campaign": sorted({r["campaign_id"] for r in insights if r.get("campaign_id")}),
        "adset": sorted({r["adset_id"] for r in insights if r.get("adset_id")}),
        "ad": sorted({r["ad_id"] for r in insights}),
    }
    ids["adcreative"] = sorted({creative_of[a] for a in ids["ad"] if creative_of.get(a)})
    accounts = sorted({r["ad_account_id"] for r in insights})
    print(f"== Meta ngày {args.day}: {len(insights)} dòng insights, tài khoản {accounts}, "
          + ", ".join(f"{len(v)} {k}" for k, v in ids.items()) + " ==")
    save("meta", "insights_hien_tai", insights)

    print("== Bước 1: Meta tự mô tả ==")
    fields = {kind: schema(kind, ids[kind][0]) for kind, _ in EDGES if ids[kind]}

    print("== Bước 2: mẫu đủ trường ==")
    dropped: list = []
    for kind, edge in EDGES:
        if kind not in fields:
            continue
        rows = [row for account in accounts
                for row in by_ids(account, edge, ids[kind], fields[kind], dropped, kind)]
        save("meta", kind, rows)
        missing = len(set(ids[kind]) - {r.get("id") for r in rows})
        if missing:
            print(f"  {kind}: {missing} id có trong insights nhưng Meta không trả (có thể đã xoá/lưu trữ)")

    span = json.dumps({"since": str(args.day), "until": str(args.day)})
    wide, placement = [], []
    for account in accounts:
        rows, _ = adaptive(lambda names, a=account: meta.get_all(f"act_{a}/insights", {
            "level": "ad", "time_range": span, "limit": 500, "fields": ",".join(names)}),
            INSIGHTS_WIDE, dropped, "insights")
        wide.extend(rows)
        placement.extend(meta.get_all(f"act_{account}/insights", {
            "level": "campaign", "time_range": span, "limit": 500,
            "breakdowns": "publisher_platform,platform_position",
            "fields": "campaign_id,campaign_name,spend,impressions,clicks,actions"}))
    save("meta", "insights_rong", wide)
    save("meta", "insights_theo_vi_tri", placement)

    save("meta", "_dropped", dropped)
    meta.tracker.save(check="explore", day=args.day)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
