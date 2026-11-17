"""MCP server của DataE: cho Claude hỏi số của DEERLY bằng cách đọc bảng gold trên BigQuery.

Vì sao có file này: Claude không gọi thẳng API Meta, Shopify (tốn quota chung với đội ads). Nó gọi các tool
dưới đây, mỗi tool chạy một câu SQL cố định, chỉ đọc, trên một bảng gold (daily_performance, mart_daily_kpi,
mart_type_day, product_daily, fct_ad_day, email_daily, dim_customer, mart_cohort_retention, mart_rfm, mart_cohort_clv, mart_product_abc).

An toàn:
- Chỉ SELECT với câu SQL viết sẵn; mọi giá trị (ngày, tên dòng, số dòng) truyền bằng query parameter, Claude không
  tự viết SQL được. Chỗ phải đổi cột (level campaign/adset/ad) chọn trong danh sách cố định.
- Khách hàng chỉ trả số tổng hợp, không bao giờ trả customer_key.
- Mỗi truy vấn quét tối đa 200 MB (BigQuery từ chối nếu vượt), không thể lố free tier.
- Không đọc dataset pii.
- Lỗi đều raise ToolError để Claude thấy lý do (mcp 2.x không giấu lỗi khác thành công).

Chạy thử từ thư mục gốc:  python mcp_server/server.py   (đứng chờ ở stdio; Claude Code tự mở qua .mcp.json)
"""

import math
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402
from mcp.server import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

MAX_BYTES = 200 * 1024 * 1024
MAX_DAYS = 800
METRICS_YML = ROOT / "transform" / "metrics.yml"  # một định nghĩa cho mọi chỉ số (tuần 3)

server = MCPServer(
    name="datae",
    instructions=(
        "Số liệu kinh doanh của shop DEERLY'S (Shopify + Meta Ads), đọc từ kho BigQuery DataE. "
        "Ngày là ngày kinh doanh theo giờ America/Phoenix. Đơn và doanh thu (rev) lấy từ Shopify; "
        "spend lấy từ Meta. MER = rev / spend, CPO = spend / orders. meta_purchases và meta_roas là số Meta "
        "tự nhận (thường cao hơn thật), chỉ để tham khảo. Hỏi tổng một khoảng ngày thì dùng performance_summary "
        "(MER tính từ tổng, không lấy trung bình MER từng ngày). Theo product type: type_performance; sản phẩm: "
        "product_performance; quảng cáo: ad_performance; email: email_performance; khách hàng: customer_summary; "
        "giữ khách theo tháng (cohort): cohort_retention; nhóm khách RFM: rfm_segments; "
        "giá trị vòng đời khách và CAC: clv_summary; mẫu nào gánh doanh thu (Pareto/ABC): product_abc; "
        "hôm qua có gì lạ (bất thường): anomaly_check; dự báo đơn 14 ngày, pacing tháng, kịch bản spend: forecast_orders. "
        "Gọi metric_definitions nếu cần định nghĩa và bẫy của từng chỉ số."
    ),
)


def param_type(value) -> str:
    """Kiểu BigQuery của tham số. Mọi giá trị Claude truyền vào đi qua tham số, không ghép vào chuỗi SQL."""
    if isinstance(value, date):
        return "DATE"
    if isinstance(value, int):
        return "INT64"
    return "STRING"


def query(sql: str, params: dict) -> list[dict]:
    """Chạy 1 câu SELECT trên BigQuery. Test thay hàm này bằng hàm giả."""
    from google.cloud import bigquery

    from pipelines.bq import mcp_client

    bq = mcp_client()   # khoá chỉ đọc silver + gold (brief), xem pipelines/bq.py
    config = bigquery.QueryJobConfig(
        maximum_bytes_billed=MAX_BYTES,
        query_parameters=[bigquery.ScalarQueryParameter(k, param_type(v), v) for k, v in params.items()],
    )
    try:
        rows = bq.query(sql.replace("{p}", bq.project), job_config=config).result()
    except Exception as error:  # lỗi BigQuery: báo cho Claude, không giấu
        raise ToolError(f"BigQuery lỗi: {str(error)[:300]}") from error
    return [dict(row.items()) for row in rows]


def plain(value):
    """Decimal/date → kiểu JSON đọc được."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def parse_range(since: str, until: str) -> tuple[date, date]:
    try:
        start, end = date.fromisoformat(since), date.fromisoformat(until)
    except ValueError as error:
        raise ToolError("Ngày phải có dạng YYYY-MM-DD, ví dụ 2026-11-07.") from error
    if start > end:
        raise ToolError(f"since ({start}) phải trước hoặc bằng until ({end}).")
    if (end - start).days + 1 > MAX_DAYS:
        raise ToolError(f"Tối đa {MAX_DAYS} ngày mỗi lần hỏi.")
    return start, end


DAILY_SQL = """
select date, orders, cancelled_orders, rev, spend, mer, cpo, meta_purchases, meta_roas
from `{p}.gold.daily_performance`
where date between @since and @until
order by date
"""

SUMMARY_SQL = """
select
  count(*)                                              as days,
  countif(spend is not null)                            as days_with_meta,
  min(date)                                             as first_date,
  max(date)                                             as last_date,
  sum(orders)                                           as orders,
  sum(cancelled_orders)                                 as cancelled_orders,
  round(sum(rev), 2)                                    as rev,
  round(sum(spend), 2)                                  as spend,
  round(safe_divide(sum(if(spend is not null, rev, 0)), sum(spend)), 4)       as mer,
  round(safe_divide(sum(spend), sum(if(spend is not null, orders, 0))), 2)    as cpo,
  sum(meta_purchases)                                   as meta_purchases,
  round(safe_divide(sum(rev), sum(orders)), 2)          as aov,
  (select round(sum(cm_est), 2) from `{p}.gold.mart_daily_kpi`
   where date between @since and @until)              as cm_est   -- công thức CM chỉ ở mart_daily_kpi
from `{p}.gold.daily_performance`
where date between @since and @until
"""


@server.tool(description="Số theo từng ngày (giờ Phoenix): đơn, đơn huỷ, rev, spend, MER, CPO, số Meta tự nhận. "
                         "since, until dạng YYYY-MM-DD.")
def daily_performance(since: str, until: str) -> dict:
    start, end = parse_range(since, until)
    rows = query(DAILY_SQL, {"since": start, "until": end})
    return {"since": str(start), "until": str(end),
            "rows": [{k: plain(v) for k, v in row.items()} for row in rows],
            "note": "spend, mer, cpo null = ngày kho chưa có dữ liệu Meta (chưa gom lịch sử hoặc chưa nạp ngày mới), "
                    "không phải 0. Ngày hôm nay (giờ Phoenix) chưa trọn, số còn thay đổi."}


@server.tool(description="Tổng một khoảng ngày (giờ Phoenix): đơn, rev, AOV, spend, MER, CPO (tính từ tổng) và CM ước. "
                         "Dùng tool này khi hỏi 'tuần này', 'tháng 10', 'so 2 khoảng'. since, until dạng YYYY-MM-DD.")
def performance_summary(since: str, until: str) -> dict:
    start, end = parse_range(since, until)
    rows = query(SUMMARY_SQL, {"since": start, "until": end})
    result = {k: plain(v) for k, v in (rows[0] if rows else {}).items()}
    if not result.get("days"):
        raise ToolError(f"Kho chưa có ngày nào trong {start} đến {end}.")
    expected = (end - start).days + 1
    notes = ["MER, CPO, CM ước chỉ tính trên các ngày có dữ liệu Meta.",
             "CM ước = rev × (1 − 28% − 3,8%) − spend, tỉ lệ giá vốn TẠM theo brief (chờ cogs.csv); không phải lãi ròng. "
             "Hoà vốn khi MER ≈ 1,47."]
    if result["days"] < expected:
        notes.append(f"Kho có dữ liệu cho {result['days']}/{expected} ngày ({result['first_date']} đến "
                     f"{result['last_date']}); phần còn lại nằm ngoài khoảng kho đã nạp.")
    if result["days_with_meta"] < result["days"]:
        notes.append(f"{result['days'] - result['days_with_meta']} ngày chưa có dữ liệu Meta (chưa nạp), "
                     "MER và CPO không tính các ngày đó.")
    return {"since": str(start), "until": str(end), **result, "notes": notes}


@server.tool(description="Định nghĩa chỉ số chung (Rev, Orders, AOV, Spend, MER, CPO, CM ước, ROAS theo type): "
                         "công thức, bảng nguồn, cách cộng nhiều ngày và bẫy. Đọc từ transform/metrics.yml.")
def metric_definitions() -> dict:
    try:
        spec = yaml.safe_load(METRICS_YML.read_text(encoding="utf-8"))
    except OSError as error:
        raise ToolError(f"Không đọc được định nghĩa ở {METRICS_YML.name}.") from error
    return {"status": spec["status"], "updated": spec["updated"], "timezone": spec["timezone"],
            "metrics": spec["metrics"]}


def rows_of(sql: str, params: dict) -> list[dict]:
    return [{k: plain(v) for k, v in row.items()} for row in query(sql, params)]


UNTYPED = "(không theo type)"
TYPE_SQL = """
select
  product_line,
  round(sum(rev), 2)                                  as rev,
  round(sum(spend), 2)                                as spend,
  round(safe_divide(sum(rev), sum(spend)), 2)         as roas
from `{p}.gold.mart_type_day`
where date between @since and @until
group by 1
order by spend desc, rev desc
"""


@server.tool(description="Doanh thu, spend Meta và ROAS theo product type (Long Sleeve, Phone Case...) trong khoảng ngày. "
                         "ROAS tính từ tổng. Spend chia theo type chỉ có từ 10/2026. since, until dạng YYYY-MM-DD.")
def type_performance(since: str, until: str) -> dict:
    start, end = parse_range(since, until)
    rows = rows_of(TYPE_SQL, {"since": start, "until": end})
    # 13/11 thử demo: Claude 2 lần lược bỏ type nhỏ (Quilt, Can Cooler) và chỉ gọi "lỗ" type ROAS < 1, bỏ sót
    # Can Cooler 1,06. Ngưỡng lỗ là ROAS hoà vốn = 1 / biên (như MER hoà vốn), nên tính sẵn danh sách.
    breakeven = 1 / margin_rate()
    # So bằng tỉ số CHƯA làm tròn (roas trả về làm tròn 2 số: 1,4655 thành 1,47 sẽ lọt). Bỏ '(không theo type)':
    # rev 0 nên roas 0 nhưng đó là spend chưa chia được, không phải type lỗ (review 13/11).
    below = [r["product_line"] for r in rows
             if r["product_line"] != UNTYPED and r["spend"] and (r["rev"] or 0) / r["spend"] < breakeven]
    untyped = sum(r["spend"] or 0 for r in rows if r["product_line"] == UNTYPED)
    return {"since": str(start), "until": str(end), "rows": rows,
            "breakeven_roas": round(breakeven, 2), "below_breakeven": below,
            # tính sẵn tổng: 13/11 Claude tự cộng spend type lỗ bị lệch ~10 USD
            "below_breakeven_spend": round(sum(r["spend"] for r in rows if r["product_line"] in below), 2),
            "untyped_spend": round(untyped, 2),
            "total": {"rev": round(sum(r["rev"] or 0 for r in rows), 2),
                      "spend": round(sum(r["spend"] or 0 for r in rows), 2)},
            "notes": [f"Liệt kê ĐỦ mọi dòng có spend > 0 (kể cả type nhỏ và '(không theo type)'), không lược bớt: "
                      f"{len(rows)} dòng.",
                      f"ROAS dưới {breakeven:.2f} (hoà vốn sau giá vốn TẠM và phí, như MER hoà vốn) là ĐANG LỖ, "
                      "không phải dưới 1. below_breakeven = các type có spend mà ROAS dưới ngưỡng này (không tính "
                      "'(không theo type)': spend đó chưa gán được type, rev của nó nằm ở các type khác).",
                      "rev = doanh thu dòng sản phẩm, CHƯA gồm ship, thuế (nhỏ hơn rev của performance_summary).",
                      "ROAS theo type gán toàn bộ doanh thu của type cho ads của type đó, kể cả đơn tự nhiên, email: "
                      "type spend nhỏ thì ROAS cao giả. Dùng để thấy chỗ cần xem kỹ, không để kết luận cắt ngân sách.",
                      "'(không theo type)' = spend campaign tên kiểu cũ (1–9/2026), không chia được."]}


PRODUCT_SQL = """
select
  product_line,
  product_subline,
  sum(orders)                     as orders,
  sum(units)                      as units,
  round(sum(line_revenue), 2)     as line_revenue
from `{p}.gold.product_daily`
where date between @since and @until
  and (@product_line = '' or product_line = @product_line)
group by 1, 2
order by line_revenue desc
"""


@server.tool(description="Bán theo dòng sản phẩm và dòng con (Sun Hoodie, Glass Ornament...) trong khoảng ngày: "
                         "số đơn, số cái, doanh thu dòng. product_line để trống = mọi dòng; hoặc ví dụ 'Long Sleeve'.")
def product_performance(since: str, until: str, product_line: str = "") -> dict:
    start, end = parse_range(since, until)
    rows = rows_of(PRODUCT_SQL, {"since": start, "until": end, "product_line": product_line.strip()})
    return {"since": str(start), "until": str(end), "product_line": product_line or "(mọi dòng)", "rows": rows,
            "notes": ["product_subline TRÙNG TÊN product_line (ví dụ dòng con 'Long Sleeve' trong Long Sleeve) nghĩa là "
                      "CHƯA PHÂN ĐƯỢC dòng con: SKU có tiền tố lẻ hoặc chưa có trong seeds/product_lines.csv. "
                      "Không phải một loại 'thường', không kết luận về nó như một sản phẩm.",
                      "line_revenue sau giảm giá, trả hàng; chưa gồm ship, thuế.",
                      "orders đếm theo ngày × dòng: 1 đơn mua 2 dòng được đếm ở cả 2, nên cộng orders các dòng "
                      "lớn hơn số đơn thật."]}


AD_LEVELS = {  # level → cột nhóm. Chọn trong danh sách cố định, không ghép chữ Claude gửi vào SQL.
    "campaign": "campaign_id, campaign_name, ad_product_line",
    "adset": "adset_id, adset_name, campaign_name",
    "ad": "ad_id, ad_name, campaign_name, creative_id",
}
AD_SQL = """
select
  {cols},
  round(sum(spend), 2)                                              as spend,
  sum(impressions)                                                  as impressions,
  sum(clicks)                                                       as clicks,
  sum(inline_link_clicks)                                           as link_clicks,
  round(100 * safe_divide(sum(clicks), sum(impressions)), 2)        as ctr_pct,
  round(safe_divide(sum(spend), sum(inline_link_clicks)), 2)        as cpc_link,
  sum(meta_add_to_cart)                                             as meta_add_to_cart,
  sum(meta_initiate_checkout)                                       as meta_initiate_checkout,
  sum(meta_purchases)                                               as meta_purchases,
  round(safe_divide(sum(meta_purchase_value), sum(spend)), 2)       as meta_roas
from `{p}.gold.fct_ad_day`
where date between @since and @until
  and spend > 0          -- lọc trước khi gom; KHÔNG viết having sum(spend): spend đã là tên cột kết quả
  and (@product_line = '' or ad_product_line = @product_line)
  and (@campaign = '' or campaign_name = @campaign)
group by {cols}
order by spend desc
limit @top
"""


@server.tool(description="Quảng cáo Meta theo campaign, adset hoặc ad trong khoảng ngày: spend, CTR, CPC, phễu, số Meta "
                         "tự nhận. level: campaign | adset | ad. top: số dòng tốn tiền nhất (tối đa 50). "
                         "Lọc (để trống = không lọc): product_line theo type đọc từ tên campaign (ví dụ 'Phone Case'), "
                         "campaign = tên campaign đầy đủ (ví dụ 'Static-Collection_AirPods Case').")
def ad_performance(since: str, until: str, level: str = "campaign", top: int = 20,
                   product_line: str = "", campaign: str = "") -> dict:
    start, end = parse_range(since, until)
    if level not in AD_LEVELS:
        raise ToolError(f"level phải là một trong {', '.join(AD_LEVELS)}.")
    top = max(1, min(int(top), 50))
    sql = AD_SQL.replace("{cols}", AD_LEVELS[level])
    rows = rows_of(sql, {"since": start, "until": end, "top": top,
                         "product_line": product_line.strip(), "campaign": campaign.strip()})
    notes = ["meta_purchases, meta_roas là số Meta tự nhận (thổi ~1,6× so với đơn Shopify): chỉ để so các ad "
             "với nhau. Hiệu quả thật cả shop xem MER ở performance_summary.",
             "Không có reach: reach không cộng được qua nhiều ngày."]
    if len(rows) == top:
        notes.append(f"Đã chạm giới hạn {top} dòng: có thể còn dòng nhỏ hơn bị cắt. Lọc theo product_line hoặc "
                     "campaign, hoặc tăng top (tối đa 50), để xem hết.")
    if not rows:
        notes.append("Không có dòng nào có spend: kiểm lại tên product_line/campaign (phải đúng từng chữ) và khoảng ngày.")
    return {"since": str(start), "until": str(end), "level": level,
            "filter": {"product_line": product_line or "(mọi type)", "campaign": campaign or "(mọi campaign)"},
            "rows": rows, "truncated": len(rows) == top, "notes": notes}


EMAIL_SQL = """
select
  channel,
  parent_name,
  sum(received)                                                as received,
  round(100 * safe_divide(sum(opened), sum(received)), 1)      as open_rate_pct,
  round(100 * safe_divide(sum(clicked), sum(received)), 2)     as click_rate_pct,
  sum(placed_orders)                                           as placed_orders,
  round(sum(placed_value), 2)                                  as placed_value
from `{p}.gold.email_daily`
where date between @since and @until
  and channel in ('campaign', 'flow')
  and (@channel = '' or channel = @channel)
group by 1, 2
order by placed_value desc
limit 30
"""


@server.tool(description="Email Klaviyo theo campaign hoặc flow trong khoảng ngày: số gửi, tỉ lệ mở, click, đơn và doanh "
                         "thu Klaviyo gán cho email. channel: để trống | campaign | flow.")
def email_performance(since: str, until: str, channel: str = "") -> dict:
    start, end = parse_range(since, until)
    if channel not in ("", "campaign", "flow"):
        raise ToolError("channel phải để trống, 'campaign' hoặc 'flow'.")
    return {"since": str(start), "until": str(end), "channel": channel or "(cả hai)",
            "rows": rows_of(EMAIL_SQL, {"since": start, "until": end, "channel": channel}),
            "notes": ["placed_orders, placed_value là Klaviyo tự gán đơn cho email, chỉ để so trong kênh email; "
                      "đơn thật của shop xem performance_summary.",
                      "Tỉ lệ mở, click tính từ tổng (tổng mở / tổng gửi)."]}


CUSTOMER_SQL = """
select
  cohort_month,
  count(*)                                               as customers,
  round(100 * countif(is_repeat) / count(*), 1)          as repeat_pct,
  round(avg(orders), 2)                                  as orders_per_customer,
  round(avg(ltv), 2)                                     as avg_ltv,
  round(safe_divide(sum(ltv), sum(orders)), 2)           as aov
from `{p}.gold.dim_customer`
where cohort_month between @cohort_from and @cohort_to
group by rollup (cohort_month)
order by cohort_month is null, cohort_month
"""


def check_month(text: str, field: str) -> str:
    try:
        date.fromisoformat(f"{text}-01")
    except ValueError as error:
        raise ToolError(f"{field} phải có dạng YYYY-MM, ví dụ 2026-09.") from error
    return text


@server.tool(description="Khách hàng theo tháng mua đầu (cohort): số khách, % khách quay lại, số đơn mỗi khách, LTV, AOV. "
                         "Chỉ số tổng hợp, không có khách cụ thể. cohort_from, cohort_to dạng YYYY-MM.")
def customer_summary(cohort_from: str, cohort_to: str) -> dict:
    start, end = check_month(cohort_from, "cohort_from"), check_month(cohort_to, "cohort_to")
    if start > end:
        raise ToolError(f"cohort_from ({start}) phải trước hoặc bằng cohort_to ({end}).")
    rows = rows_of(CUSTOMER_SQL, {"cohort_from": start, "cohort_to": end})
    for row in rows:
        if row["cohort_month"] is None:
            row["cohort_month"] = "(tổng)"
    return {"cohort_from": start, "cohort_to": end, "rows": rows,
            "notes": ["Khách = 1 email (customer_key, đã hash). Đơn không có email không tính.",
                      "LTV = tổng rev đã trừ hoàn của mọi đơn tới lần nạp gần nhất: cohort gần đây có ít thời gian "
                      "mua lại hơn, nên repeat_pct và LTV thấp hơn là bình thường, không so thẳng với cohort cũ."]}


COHORT_SQL = """
select
  cohort_month,
  cohort_size,
  month_offset,
  active_customers,
  retention_pct,
  ci_low,
  ci_high,
  is_complete
from `{p}.gold.mart_cohort_retention`
where cohort_month between @cohort_from and @cohort_to
  and month_offset between 1 and @max_offset
order by cohort_month, month_offset
"""
SMALL_COHORT = 100  # bài học mô hình 1: dưới ~100 khách thì tỉ lệ không đáng tin, gộp theo quý


@server.tool(description="Bảng giữ khách theo cohort (mô hình 1): với mỗi tháng mua đầu, % khách còn mua ở tháng thứ "
                         "1, 2, 3... kèm khoảng tin cậy Wilson 95%. cohort_from, cohort_to dạng YYYY-MM; max_offset = "
                         "số tháng xem tối đa (mặc định 6, tối đa 24). Khác customer_summary (% quay lại tính dồn).")
def cohort_retention(cohort_from: str, cohort_to: str, max_offset: int = 6) -> dict:
    start, end = check_month(cohort_from, "cohort_from"), check_month(cohort_to, "cohort_to")
    if start > end:
        raise ToolError(f"cohort_from ({start}) phải trước hoặc bằng cohort_to ({end}).")
    max_offset = max(1, min(int(max_offset), 24))
    cohorts: dict[str, dict] = {}
    for row in rows_of(COHORT_SQL, {"cohort_from": start, "cohort_to": end, "max_offset": max_offset}):
        c = cohorts.setdefault(row["cohort_month"], {
            "cohort_month": row["cohort_month"], "cohort_size": row["cohort_size"],
            "small_cohort": row["cohort_size"] < SMALL_COHORT, "months": []})
        c["months"].append({"k": row["month_offset"], "retention_pct": row["retention_pct"],
                            "ci_low": row["ci_low"], "ci_high": row["ci_high"],
                            "active_customers": row["active_customers"], "complete": row["is_complete"]})
    small = [m for m, c in cohorts.items() if c["small_cohort"]]
    notes = ["Tháng k = tháng LỊCH thứ k sau tháng mua đầu (cohort 2026-06: k=1 là tháng 7), không phải 30 ngày.",
             "Mỗi ô đếm riêng tháng đó, không cộng dồn; không cộng các tháng thành '% quay lại' (xem customer_summary).",
             "Chỉ coi hai cohort khác nhau thật khi khoảng ci_low–ci_high KHÔNG chồng nhau.",
             "complete = false: tháng đang chạy, số còn tăng; các ô này cùng một đường chéo, đừng đọc là khách bỏ đi.",
             "Kho có Shopify từ 11/2024: cohort 2024-11 gồm cả khách mua trước đó."]
    if small:
        notes.insert(0, f"Cohort dưới {SMALL_COHORT} khách, tỉ lệ chưa đáng tin (khoảng tin cậy rất rộng), không "
                        f"dùng để kết luận; nên gộp theo quý: {', '.join(small)}.")
    if not cohorts:
        notes.insert(0, "Không có cohort nào trong khoảng này.")
    return {"cohort_from": start, "cohort_to": end, "max_offset": max_offset,
            "cohorts": list(cohorts.values()), "notes": notes}


RFM_SQL = """
select
  segment,
  any_value(as_of_date)                                               as as_of_date,
  count(*)                                                            as customers,
  round(100 * count(*) / sum(count(*)) over (), 1)                    as pct_customers,
  round(avg(recency_days))                                            as avg_recency_days,
  round(safe_divide(sum(frequency), count(*)), 2)                     as orders_per_customer,
  round(safe_divide(sum(monetary), count(*)), 2)                      as avg_spend,
  round(sum(monetary), 2)                                             as revenue,
  round(100 * sum(monetary) / sum(sum(monetary)) over (), 1)          as pct_revenue
from `{p}.gold.mart_rfm`
group by segment
order by customers desc
"""
RFM_RULES = {  # luật gán nhóm (mart_rfm.sql), để Claude giải thích nhóm là ai mà không phải đoán
    "Đã mất": "hơn 365 ngày chưa mua",
    "Không thể để mất": "181–365 ngày chưa mua, chi tiêu top 20% (phần lớn là khách 1 đơn to)",
    "Có nguy cơ": "181–365 ngày chưa mua, từng mua từ 2 lần",
    "Champions": "mua từ 3 lần, đơn cuối trong 60 ngày",
    "Loyal": "mua từ 3 lần, đơn cuối 61–180 ngày trước",
    "Mới quay lại": "mua đúng 2 lần, đơn cuối trong 60 ngày",
    "Cần chú ý": "mua đúng 2 lần, đơn cuối 61–180 ngày trước",
    "Khách mới": "mua 1 lần, trong 60 ngày (luôn tách riêng, không so với khách cũ)",
    "Ngủ đông": "mua 1 lần, đơn đó 61–365 ngày trước",
}
SMALL_SEGMENT = 30  # nhóm quá ít khách thì số trung bình dao động mạnh


@server.tool(description="Nhóm khách RFM (mô hình 2) tại ngày dữ liệu mới nhất: số khách, % khách, số ngày từ đơn cuối "
                         "trung bình, đơn mỗi khách, chi tiêu trung bình, % doanh thu của từng nhóm (Champions, Khách mới, "
                         "Ngủ đông, Có nguy cơ...). Chỉ số tổng hợp theo nhóm, không có khách cụ thể.")
def rfm_segments() -> dict:
    rows = rows_of(RFM_SQL, {})
    if not rows:
        raise ToolError("Bảng mart_rfm chưa có dữ liệu.")
    as_of = rows[0]["as_of_date"]
    segments = []
    for row in rows:
        row.pop("as_of_date", None)
        row["rule"] = RFM_RULES.get(row["segment"], "(không rõ)")
        row["small_segment"] = row["customers"] < SMALL_SEGMENT
        segments.append(row)
    notes = [f"Ảnh chụp tại {as_of} (ngày dữ liệu mới nhất). Mỗi lần nạp mới khách có thể đổi nhóm.",
             "Chỉ đếm đơn không huỷ, nên số đơn mỗi khách khác customer_summary.",
             "Khách mới luôn tách riêng, không so với khách cũ (chưa thể mua nhiều lần).",
             "Đã backtest (chia nhóm tại 1/7 và 1/8/2026, xem 90 ngày sau): % mua lại trong 90 ngày Champions ~35%, "
             "Mới quay lại ~20%, Khách mới ~9%, Ngủ đông ~4%, Đã mất ~2%, cùng thứ tự ở 2 mốc. Bốn nhóm đầu tách nhau "
             "thật; Ngủ đông và Đã mất chưa tách được.",
             "Loyal, Cần chú ý, Không thể để mất, Có nguy cơ chưa kiểm được (quá ít khách ở các mốc backtest): "
             "không trình bày thứ hạng của chúng như đã chứng minh.",
             "Ngủ đông tự mua lại ~4% trong 90 ngày (~1%/tháng) khi chưa có winback; winback chỉ được tính phần vượt "
             "trên mức đó. Không dùng % giữ khách của cohort cho nhóm này (cohort gồm cả khách mua nhiều lần).",
             "Ngưỡng 60/180/365 ngày dựa trên khoảng cách đơn 1 → 2 thật (trung vị 17 ngày), nhưng còn thiên ngắn vì "
             "shop trẻ."]
    small = [r["segment"] for r in segments if r["small_segment"]]
    if small:
        notes.insert(1, f"Nhóm dưới {SMALL_SEGMENT} khách, số trung bình dao động mạnh, không kết luận: "
                        f"{', '.join(small)}.")
    return {"as_of_date": as_of, "segments": segments, "notes": notes}


CLV_SQL = """
with month_spend as (
  select format_date('%Y-%m', date) as cohort_month,
         sum(spend) as month_spend,
         countif(spend is null) as days_without_meta
  from `{p}.gold.daily_performance`
  group by 1
)
select
  c.cohort_month,
  c.cohort_size,
  c.month_offset,
  c.avg_cum_rev,
  c.median_cum_rev,
  c.ci_low,
  c.ci_high,
  c.multiple_of_first,
  c.is_complete,
  m.month_spend,
  m.days_without_meta
from `{p}.gold.mart_cohort_clv` c
left join month_spend m using (cohort_month)
where c.cohort_month between @cohort_from and @cohort_to
  and c.month_offset <= @max_offset
order by c.cohort_month, c.month_offset
"""
DBT_PROJECT = ROOT / "transform" / "dbt_project.yml"


def margin_rate() -> float:
    """1 − cogs_rate − fee_rate, đọc từ vars dbt (một chỗ định nghĩa, giống cm_est)."""
    try:
        v = yaml.safe_load(DBT_PROJECT.read_text(encoding="ascii"))["vars"]
        return 1 - float(v["cogs_rate"]) - float(v["fee_rate"])
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ToolError("Không đọc được cogs_rate, fee_rate trong dbt_project.yml.") from error


@server.tool(description="CLV lịch sử theo cohort (mô hình 3): doanh thu cộng dồn mỗi khách tới tháng thứ k (trung bình, "
                         "trung vị, khoảng tin cậy, bội số so với tháng đầu), kèm CAC khách mới của tháng cohort (spend Meta "
                         "/ số khách mới) và tỉ lệ CLV lợi nhuận ước / CAC. cohort_from, cohort_to dạng YYYY-MM; max_offset "
                         "mặc định 6, tối đa 24.")
def clv_summary(cohort_from: str, cohort_to: str, max_offset: int = 6) -> dict:
    start, end = check_month(cohort_from, "cohort_from"), check_month(cohort_to, "cohort_to")
    if start > end:
        raise ToolError(f"cohort_from ({start}) phải trước hoặc bằng cohort_to ({end}).")
    max_offset = max(0, min(int(max_offset), 24))
    rate = margin_rate()
    cohorts: dict[str, dict] = {}
    for row in rows_of(CLV_SQL, {"cohort_from": start, "cohort_to": end, "max_offset": max_offset}):
        c = cohorts.get(row["cohort_month"])
        if c is None:
            size, spend = row["cohort_size"], row["month_spend"]
            full_meta = spend is not None and not row["days_without_meta"]
            cac = round(spend / size, 2) if full_meta and size else None
            c = cohorts[row["cohort_month"]] = {
                "cohort_month": row["cohort_month"], "cohort_size": size, "small_cohort": size < SMALL_COHORT,
                "month_spend": spend if full_meta else None, "cac_new_customer": cac, "months": []}
        clv = row["avg_cum_rev"]
        margin = round(clv * rate, 2) if clv is not None else None
        c["months"].append({
            "k": row["month_offset"], "avg_clv_rev": clv, "median_clv_rev": row["median_cum_rev"],
            "ci_low": row["ci_low"], "ci_high": row["ci_high"], "multiple_of_first": row["multiple_of_first"],
            "clv_margin_est": margin,
            "clv_margin_to_cac": round(margin / c["cac_new_customer"], 2) if margin and c["cac_new_customer"] else None,
            "complete": row["is_complete"]})
    notes = [
        "CLV ở đây là DOANH THU cộng dồn đã xảy ra (lịch sử), không phải dự đoán. Mô hình dự đoán (BG/NBD) hoãn tới sau "
        "2/2027 vì chưa có trọn 1 năm dữ liệu khách.",
        f"clv_margin_est = CLV doanh thu × {rate:.3f} (1 − giá vốn 28% − phí 3,8%, tỉ lệ TẠM theo brief, chờ cogs.csv). "
        "Chưa trừ ship thực trả.",
        "cac_new_customer = spend Meta cả tháng cohort / số khách mới có email của tháng đó. Giả định toàn bộ spend là "
        "để kéo khách mới (spend cũng mang về đơn của khách cũ), nên CAC này hơi cao hơn thật; khách không email không "
        "được đếm, nên lại hơi cao thêm. Chỉ có Meta.",
        "clv_margin_to_cac dưới 1 = lợi nhuận ước của khách tới tháng k chưa bù được chi phí kéo khách. Ngành hay nhắm "
        "khoảng 3, nhưng ở đây CLV mới vài tháng nên chỉ đọc như thời gian hoàn vốn.",
        "Luôn đọc kèm median_clv_rev: khách điển hình chỉ mua 1 đơn (~46 USD), trung bình bị vài khách mua nhiều kéo lên.",
        "complete = false: tháng đang chạy, CLV còn tăng. CLV 12 tháng chưa đáng tin (cohort đủ 12 tháng chỉ ~144 khách).",
    ]
    small = [m for m, c in cohorts.items() if c["small_cohort"]]
    if small:
        notes.insert(0, f"Cohort dưới {SMALL_COHORT} khách, CLV dao động mạnh, không kết luận: {', '.join(small)}.")
    no_cac = [m for m, c in cohorts.items() if c["cac_new_customer"] is None]
    if no_cac:
        notes.append(f"Không tính được CAC (tháng chưa có đủ dữ liệu Meta, kho có Meta từ 1/2026): {', '.join(no_cac)}.")
    return {"cohort_from": start, "cohort_to": end, "max_offset": max_offset, "margin_rate": round(rate, 3),
            "cohorts": list(cohorts.values()), "notes": notes}


ABC_SUMMARY_SQL = """
select
  case when @product_line = '' then abc_class else abc_in_line end   as abc_group,
  any_value(as_of_date)                                              as as_of_date,
  any_value(window_start)                                            as window_start,
  count(*)                                                           as products,
  round(sum(revenue), 2)                                             as group_revenue,
  round(avg(units), 1)                                               as avg_units
from `{p}.gold.mart_product_abc`
where (@product_line = '' or product_line = @product_line)
group by abc_group
"""
ABC_TOP_SQL = """
select product_title, product_line, product_subline, theme, species, abc_class, abc_in_line,
       revenue, units, orders, product_url, is_live
from `{p}.gold.mart_product_abc`
where not is_new and units > 0
  and (@product_line = '' or product_line = @product_line)
order by revenue desc, product_key
limit @top
"""
ABC_NEW_SQL = """
select product_title, product_line, product_subline, theme, created_date, age_days,
       revenue, units, rev_per_live_day, product_url
from `{p}.gold.mart_product_abc`
where is_new and units > 0
  and (@product_line = '' or product_line = @product_line)
order by rev_per_live_day desc, product_key
limit 10
"""
ABC_GINI_SQL = """
with x as (
  select revenue,
         row_number() over (order by revenue, product_key) as i,
         count(*) over ()                                   as n,
         sum(revenue) over ()                               as total
  from `{p}.gold.mart_product_abc`
  where not is_new and (@product_line = '' or product_line = @product_line)
)
select
  any_value(n)                                                                     as mature_products,
  round(safe_divide(2 * sum(i * revenue), any_value(n) * any_value(total))
        - (any_value(n) + 1) / any_value(n), 3)                                    as gini_incl_dead
from x
"""
ABC_XYZ_SQL = """
select cap_do, nhom, product_line, xyz_class, weeks_live, units_12w, revenue_12w, mean_week_units,
       cv, noise_cv, trend_ratio, first_sale_date
from `{p}.gold.mart_xyz_group`
where (@product_line = '' or product_line = @product_line)
  and units_12w > 0
order by cap_do, revenue_12w desc
"""
ABC_ORDER = {"A": 1, "B": 2, "C": 3, "D": 4, "Mới": 5}


@server.tool(description="Pareto / ABC mẫu (mô hình 5), 90 ngày gần nhất: số mẫu và % doanh thu của nhóm A (80% doanh thu "
                         "đầu), B, C, D (đang mở bán mà 0 cái), Mới (dưới 30 ngày tuổi); hệ số Gini; top mẫu đủ tuổi bán "
                         "chạy kèm tên và link; top mẫu mới theo doanh thu mỗi ngày mở bán. product_line để trống = cả shop "
                         "(xếp chung), hoặc ví dụ 'Long Sleeve' (xếp riêng trong dòng). top tối đa 50. Kèm XYZ (bán đều hay "
                         "thất thường, có xu hướng tăng/giảm) theo dòng con và biến thể.")
def product_abc(product_line: str = "", top: int = 20) -> dict:
    line = product_line.strip()
    top = max(1, min(int(top), 50))
    groups = sorted(rows_of(ABC_SUMMARY_SQL, {"product_line": line}), key=lambda r: ABC_ORDER.get(r["abc_group"], 9))
    if not groups:
        raise ToolError(f"Không có mẫu nào cho product_line '{line}'. Tên phải đúng từng chữ, ví dụ 'Long Sleeve'.")
    as_of, start = groups[0].pop("as_of_date"), groups[0].pop("window_start")
    mature_rev = sum(g["group_revenue"] for g in groups if g["abc_group"] != "Mới") or 0
    all_rev = sum(g["group_revenue"] for g in groups) or 0
    for g in groups:
        g.pop("as_of_date", None)
        g.pop("window_start", None)
        g["pct_of_mature_revenue"] = (round(100 * g["group_revenue"] / mature_rev, 1)
                                      if g["abc_group"] != "Mới" and mature_rev else None)
        g["pct_of_all_revenue"] = round(100 * g["group_revenue"] / all_rev, 1) if all_rev else None
    gini = rows_of(ABC_GINI_SQL, {"product_line": line})
    top_rows = rows_of(ABC_TOP_SQL, {"product_line": line, "top": top})
    new_rows = rows_of(ABC_NEW_SQL, {"product_line": line})
    xyz_rows = rows_of(ABC_XYZ_SQL, {"product_line": line})
    notes = [
        f"Cửa sổ {start} tới {as_of} (90 ngày). Doanh thu dòng sau giảm giá, trả hàng; chưa ship, thuế, giá vốn.",
        "A/B/C xếp trong mẫu ĐỦ TUỔI (từ 30 ngày): A = 80% doanh thu đủ tuổi đầu, B 80–95%, C 95–100%. Mới đứng riêng, "
        "so bằng rev_per_live_day.",
        "ABC đo kết quả, không đo tiềm năng: mẫu A có thể chỉ là mẫu được chạy ads (chưa nối ad với mẫu). D là chưa bán "
        "được, có thể là chưa ai nhìn thấy.",
        "Kiểm định 2 kỳ 90 ngày: 53% mẫu A vẫn A, 80% vẫn A hoặc B, 7% rơi xuống D. B và C rất nhiễu (64% mẫu C sang D "
        "hoặc bị ẩn): với B, C nên quyết định ở cấp chủ đề, loài, không theo từng mẫu.",
        "Gini tính cả mẫu D (đúng cách). Bỏ mẫu 0 cái thì Gini thấp hơn thật.",
        "Nhạy mùa vụ: cửa sổ 90 ngày vào tháng 11 làm Ornament phình to.",
        "XYZ (xyz_by_group): đọc ở cấp dòng con, biến thể; KHÔNG đọc XYZ từng mẫu (mẫu bán 1–2 cái/tuần nên cv chủ "
        "yếu là may rủi). X cv < 0,5 đều, Y 0,5–1, Z > 1; chưa đủ dữ liệu khi < 5 cái/tuần hoặc < 8 tuần.",
        "Luôn đọc XYZ kèm trend_ratio (4 tuần cuối ÷ 4 tuần đầu): cv cao có thể chỉ vì đang vào mùa (Y mùa vụ), "
        "X vẫn có thể đang giảm. cv gần noise_cv thì dao động chủ yếu là ngẫu nhiên. 12 tuần chưa chứng minh "
        "mùa vụ lặp lại.",
    ]
    if line:
        notes.insert(0, f"Đã lọc product_line = '{line}': nhóm là abc_in_line (xếp riêng trong dòng này).")
    return {"product_line": line or "(cả shop)", "as_of_date": as_of, "window_start": start,
            "groups": groups, "concentration": gini[0] if gini else None,
            "top_products": top_rows, "top_new_products": new_rows, "xyz_by_group": xyz_rows, "notes": notes}


ANOMALY_SQL = """
with m as (select max(date) as last_date from `{p}.gold.mart_anomaly_daily`),
r as (select coalesce(safe_cast(nullif(@until, '') as date), m.last_date) as e from m)
select a.date, a.weekday, a.event, a.metric, a.method, a.value, a.expected, a.pct_vs_expected, a.score, a.direction,
       a.level, m.last_date
from `{p}.gold.mart_anomaly_daily` a
cross join m
cross join r
where a.date between date_sub(r.e, interval @span day) and r.e
order by a.date desc, a.metric
"""
ANOMALY_MEANING = {  # chiều nào là xấu, để Claude không đọc "cao" thành "tốt"
    "orders": "thấp là xấu", "gross_sales": "thấp là xấu", "mer": "thấp là xấu", "new_share": "thấp là xấu",
    "email_orders": "thấp là xấu (flow tắt); cao thường là ngày gửi campaign",
    "cpo": "cao là xấu", "cancel_rate": "cao là xấu", "refunds": "cao là xấu",
    "spend": "quyết định của shop; về 0 hay tụt mạnh = kiểm tài khoản ads, thẻ",
}
ANOMALY_RANK = {"cần xử lý": 0, "để ý": 1, "(không tính được)": 2, "bình thường": 3}
MAX_ANOMALY_DAYS = 31


@server.tool(description="Bất thường kinh doanh (mô hình 8): 'hôm qua có gì lạ không?'. So mỗi ngày đã trọn với kỳ vọng "
                         "(mức 7 ngày trước × hệ số thứ; chỉ số hiếm so với trung bình 28 ngày) cho 9 chỉ số: orders, "
                         "gross_sales (lúc đặt), spend, cpo, mer, new_share, cancel_rate, refunds, email_orders. "
                         "until để trống = ngày mới nhất trong bảng; days = số ngày nhìn lại (1–31). Trả đủ 9 chỉ số của "
                         "ngày cuối và mọi báo động trong khoảng, kèm kiểm dữ liệu đã nạp đủ chưa.")
def anomaly_check(until: str = "", days: int = 1) -> dict:
    day = until.strip()
    if day:
        try:
            date.fromisoformat(day)
        except ValueError as error:
            raise ToolError("until phải có dạng YYYY-MM-DD, ví dụ 2026-11-10, hoặc để trống.") from error
    days = max(1, min(int(days), MAX_ANOMALY_DAYS))
    rows = rows_of(ANOMALY_SQL, {"until": day, "span": days - 1})
    if not rows:
        raise ToolError(f"Không có dòng nào tới {day or 'ngày mới nhất'} trong mart_anomaly_daily "
                        "(bảng tính từ khoảng 3/5/2026, chỉ ngày đã trọn).")
    last_date = rows[0].pop("last_date")
    for r in rows[1:]:
        r.pop("last_date", None)
    end = rows[0]["date"]
    latest = [r for r in rows if r["date"] == end]
    alerts = sorted((r for r in rows if r["level"] in ("cần xử lý", "để ý")),
                    key=lambda r: (ANOMALY_RANK[r["level"]], r["date"] != end, -abs(r["score"] or 0)))
    for r in latest + alerts:
        r["meaning"] = ANOMALY_MEANING.get(r["metric"], "")

    # Bất thường DỮ LIỆU trước bất thường kinh doanh (bài học 4a)
    data_checks = []
    expected_last = last_complete_day()
    if not day and str(last_date) < expected_last:
        data_checks.append(f"Bảng mới tới {last_date}, nhưng ngày đã trọn gần nhất là {expected_last}, nên số mới nhất "
                           "chưa phải hôm qua. Thường là do lần nạp gần nhất chạy trước nửa đêm Phoenix (pipeline 8h sáng "
                           "giờ VN = 18h Phoenix hôm trước): ngày đó mới nạp dở nên bảng cố ý bỏ. Cũng có thể kho chưa nạp "
                           "hoặc chưa dbt build. Muốn có ngày này: chạy lại pipeline + dbt build sau 14h giờ VN.")
    have = {r["metric"] for r in latest}
    if {"spend", "cpo", "mer"} - have:
        data_checks.append(f"Ngày {end} chưa có spend/cpo/mer: Meta chưa nạp ngày này (null, không phải 0).")
    missing = set(ANOMALY_MEANING) - have - {"spend", "cpo", "mer"}
    if missing:
        data_checks.append(f"Ngày {end} thiếu {', '.join(sorted(missing))}.")

    notes = [
        "Đọc data_checks trước: thiếu dữ liệu thì 'tụt' là giả. Sau đó mới xét alerts.",
        "Mức: để ý khi |score| ≥ 3,5; cần xử lý khi ≥ 6 hoặc ≥ 3,5 hai ngày liền cùng chiều. Score = lệch ÷ độ rộng "
        "(có sàn nhiễu); shop ít đơn thì lệch nhiều % vẫn có thể score nhỏ.",
        "Đổi mức (tăng ngân sách, vào mùa) chỉ báo vài ngày đầu rồi mức 7 ngày bắt kịp; tụt TỪ TỪ cả tuần không "
        "bao giờ báo (ví dụ 10–16/9 orders thấp hơn kỳ vọng 5/7 ngày). Hỏi xu hướng thì dùng daily_performance.",
        "Cột event: tên sự kiện của ngày (lễ Mỹ, BFCM, ngày tặng quà; seed events). Báo động vào ngày có event thường "
        "do chính sự kiện, nói rõ như vậy. Ngày sự kiện không làm mốc cho ngày khác, nên tuần sau lễ không bị báo "
        "nhầm. Lịch CHƯA có ngày sale riêng của shop và ngày gửi campaign email: những ngày đó vẫn bị báo.",
        "Kiểm định 12/11: 11,5% số ngày có ít nhất 1 báo động, phần lớn giải thích được.",
        "gross_sales là total_price lúc đặt (không phải rev); mer ở đây tính từ gross_sales. Chỉ kiểm tổng shop.",
        f"MER hoà vốn sau giá vốn và phí ≈ {1 / margin_rate():.2f} (1 ÷ biên {margin_rate():.3f}). MER dưới mức này là "
        "ĐANG LỖ, không phải 'hoà vốn tiền quảng cáo'; MER 1 chỉ là doanh thu bằng tiền ads.",
        "Một sự cố thường làm nhiều chỉ số cùng lệch (orders tụt kéo gross_sales, cpo): kể như một chuyện, bắt đầu "
        "từ chỉ số gốc.",
    ]
    return {"until": str(end), "days": days, "last_date_in_table": str(last_date),
            "data_checks": data_checks, "latest_day": latest, "alerts": alerts, "notes": notes}


FORECAST_SQL = """
select origin, date, h, weekday, fc, lo, hi, k, train_from, train_to, backtest_wape_pct, backtest_cover_pct,
       backtest_total_p80_pct, backtest_total_bias_pct
from `{p}.gold.forecast_daily`
order by date
"""
SPEND_MODEL_SQL = """
select origin, intercept, b_log_spend, dow_tue, dow_wed, dow_thu, dow_fri, dow_sat, dow_sun, sigma, t80, k,
       spend_min, spend_max, spend_7d_mean, n_days, train_from, train_to, backtest_wape_pct, backtest_cover_pct,
       backtest_total_p80_pct, backtest_total_bias_pct
from `{p}.gold.forecast_spend_model`
"""
EVENTS_SQL = """
select date, event, kind
from `{p}.gold.dim_event`
where date between @since and @until
order by date
"""
MTD_SQL = """
select coalesce(sum(orders), 0) as orders, count(*) as days
from `{p}.gold.daily_performance`
where date between @month_start and @until
"""
FORECAST_STALE_DAYS = 8   # publish chạy mỗi tuần; mốc cũ hơn 8 ngày so với hôm qua thì báo
PACING_MAX_DAYS = 14      # Huy Anh chốt 12/11: chỉ dùng phần đã kiểm (14 ngày)
DOW_COLS = ["dow_tue", "dow_wed", "dow_thu", "dow_fri", "dow_sat", "dow_sun"]   # thứ Hai là gốc (0)


def total_range(total: float, p80_pct: float) -> list:
    return [round(total * (1 - p80_pct / 100), 0), round(total * (1 + p80_pct / 100), 0)]


def spend_scenario(model: dict, spend_per_day: float, days: list[date]) -> list[dict]:
    """Kịch bản spend_reg: đơn mỗi ngày = exp(intercept + b × log(spend) + hệ số thứ) (trung vị),
    khoảng 80% = exp(mu ± t80 × sigma × k). Cùng công thức với forecast/backtest.f_spend_reg."""

    out = []
    for d in days:
        dow = d.weekday()
        mu = model["intercept"] + model["b_log_spend"] * math.log(spend_per_day) + (
            model[DOW_COLS[dow - 1]] if dow else 0.0)
        half = model["t80"] * model["sigma"] * model["k"]
        out.append({"date": str(d), "weekday": d.strftime("%a"), "orders": round(math.exp(mu), 1),
                    "lo": round(math.exp(mu - half), 1), "hi": round(math.exp(mu + half), 1)})
    return out


@server.tool(description="Dự báo orders 14 ngày tới (mô hình 8). spend_per_day để trống = 'nếu cứ chạy như hiện tại' "
                         "(ETS, kèm pacing tháng khi tháng còn ≤ 14 ngày); điền số USD/ngày = kịch bản 'nếu chi X USD "
                         "mỗi ngày trong 14 ngày tới' (hồi quy đơn theo spend, chỉ trong khoảng spend đã thấy). "
                         "Luôn có khoảng 80%, sai số backtest và giả định.")
def forecast_orders(spend_per_day: float | None = None) -> dict:
    rows = rows_of(FORECAST_SQL, {})
    if not rows:
        raise ToolError("Chưa có dự báo: bảng gold.forecast_daily trống. Chạy python -m forecast.publish sau dbt build.")
    model_rows = rows_of(SPEND_MODEL_SQL, {})
    window = (date.fromisoformat(rows[0]["date"]), date.fromisoformat(rows[-1]["date"]))
    events = rows_of(EVENTS_SQL, {"since": window[0], "until": window[1]})
    origin = date.fromisoformat(rows[0]["origin"])
    yesterday = date.fromisoformat(last_complete_day())
    data_checks = []
    if (yesterday - origin).days > FORECAST_STALE_DAYS:
        data_checks.append(f"Dự báo lập từ mốc {origin}, đã cũ {(yesterday - origin).days} ngày: chạy lại "
                           "python -m forecast.publish (sau khi nạp dữ liệu và dbt build).")
    notes = [
        f"Backtest 16 mốc (7–10/2026): ETS sai lệch WAPE {rows[0]['backtest_wape_pct']}%, thắng mốc ngây thơ ~17%; "
        f"khoảng 80% đã nới k = {rows[0]['k']}, nhưng kiểm NGOÀI MẪU chỉ phủ ~{rows[0]['backtest_cover_pct']}% số ngày. "
        "Thị trường đổi (như tháng 9) thì lệch nặng hơn.",
        "Không đoán được cú sốc (tài khoản ads khoá, mẫu lan truyền) và CHƯA có Q4 ở quy mô này: Black Friday, Cyber "
        "Monday, hạn giao Giáng sinh có thể vượt xa khoảng.",
        "Chỉ dự báo 14 ngày. Tổng 30 ngày đã kiểm lệch trung bình 24% (tệ nhất 63%) vì phụ thuộc quyết định ngân "
        "sách, nên không đưa số cả tháng khi tháng còn hơn 14 ngày.",
        "Đơn là số đơn Shopify (kể cả đơn huỷ, như orders của daily_performance).",
        f"Ngày {origin + timedelta(days=1)} (ngày đầu dự báo) có thể đã có số NẠP DỞ trong daily_performance (pipeline "
        "chạy lúc ~18h Phoenix): không so số dở đó với dự báo, cũng không cộng vào tổng 'đã qua'. Chỉ so ngày đã trọn "
        f"(tới {yesterday}).",
        "Khoảng cho TỔNG 14 ngày là total_14d_range (± p80 lệch tổng trong backtest: 80% số mốc lệch không quá mức "
        "đó). Không cộng lo/hi từng ngày, không dùng WAPE ngày làm sai số của tổng.",
    ]
    out = {"origin": str(origin), "data_checks": data_checks}

    if spend_per_day is None:
        out["mode"] = "ets (nếu cứ chạy như hiện tại)"
        out["days"] = [{k: r[k] for k in ("date", "weekday", "h", "fc", "lo", "hi")} for r in rows]
        out["total_14d"] = round(sum(r["fc"] for r in rows), 0)
        out["total_14d_range"] = total_range(out["total_14d"], rows[0]["backtest_total_p80_pct"])
        out["total_14d_backtest"] = {"p80_abs_pct": rows[0]["backtest_total_p80_pct"],
                                     "bias_pct": rows[0]["backtest_total_bias_pct"]}
        first = date.fromisoformat(rows[0]["date"])
        month_end = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        left = [r for r in rows if r["date"] <= str(month_end)]
        if (month_end - origin).days <= PACING_MAX_DAYS:
            mtd = rows_of(MTD_SQL, {"month_start": first.replace(day=1), "until": origin})[0]
            out["pacing"] = {
                "month": first.strftime("%Y-%m"), "orders_so_far": mtd["orders"], "days_so_far": mtd["days"],
                "forecast_rest": round(sum(r["fc"] for r in left), 0),
                "month_total": round(mtd["orders"] + sum(r["fc"] for r in left), 0),
                "month_total_range": [round(mtd["orders"] + sum(r["lo"] for r in left), 0),
                                      round(mtd["orders"] + sum(r["hi"] for r in left), 0)],
                "note": "Khoảng tổng cộng từ khoảng từng ngày nên rộng hơn thật (các ngày không lệch cùng chiều hết).",
            }
        else:
            out["pacing"] = (f"Tháng {first.strftime('%Y-%m')} còn {(month_end - origin).days} ngày sau mốc (> "
                             f"{PACING_MAX_DAYS}): chưa đoán được tổng tháng. Hỏi theo kịch bản spend_per_day, hoặc hỏi "
                             "lại khi tháng còn ≤ 14 ngày.")
    else:
        if not model_rows:
            raise ToolError("Chưa có hệ số spend: bảng gold.forecast_spend_model trống. Chạy python -m forecast.publish.")
        m = model_rows[0]
        spend = float(spend_per_day)
        # In cận dưới làm tròn LÊN, cận trên làm tròn XUỐNG: số in ra phải tự dùng được. 13/11: spend_max 4.174,6 in
        # thành "4,175", Claude thử đúng 4175 (theo lời gợi ý "kịch bản ở spend_max") thì bị từ chối.
        ok_min, ok_max = math.ceil(m["spend_min"]), math.floor(m["spend_max"])
        if not (m["spend_min"] <= spend <= m["spend_max"]):
            raise ToolError(f"spend_per_day {spend:,.0f} nằm ngoài khoảng spend 8 tuần học ({ok_min:,}–"
                            f"{ok_max:,} USD/ngày, {m['train_from']} tới {m['train_to']}). Ngoài khoảng này "
                            "mô hình chưa từng thấy, không đưa số. KHÔNG tự ngoại suy bằng hệ số spend (kể cả gọi là "
                            "'mức trần'): ngoài khoảng đã thấy quan hệ spend → đơn không còn đúng (khán giả bão hoà, "
                            "học lại), con số ngoại suy dễ bị dùng như dự báo. "
                            # quá thấp thì gợi ý mức thấp nhất, không khuyên tăng ngân sách (review 13/11)
                            + (f"Thay vào đó: kịch bản ở {ok_max:,} USD/ngày (mức cao nhất đã thấy), và đề xuất tăng "
                               "ngân sách từng bậc rồi theo dõi CPO bằng anomaly_check để có dữ liệu thật."
                               if spend > m["spend_max"] else
                               f"Thay vào đó: kịch bản ở {ok_min:,} USD/ngày (mức thấp nhất đã thấy). Muốn giảm sâu "
                               "hơn thì giảm từng bậc và theo dõi đơn bằng anomaly_check."))
        days = [date.fromisoformat(r["date"]) for r in rows]
        scen = spend_scenario(m, spend, days)
        total = sum(d["orders"] for d in scen)
        out["mode"] = f"kịch bản spend {spend:,.0f} USD/ngày"
        out["days"] = scen
        out["total_14d"] = round(total, 0)
        out["total_14d_range"] = total_range(out["total_14d"], m["backtest_total_p80_pct"])
        out["total_14d_backtest"] = {"p80_abs_pct": m["backtest_total_p80_pct"], "bias_pct": m["backtest_total_bias_pct"]}
        out["cpo_est"] = round(14 * spend / total, 2) if total else None
        out["spend_model"] = {"b_log_spend": round(m["b_log_spend"], 3), "spend_7d_mean": m["spend_7d_mean"],
                              "spend_range": [m["spend_min"], m["spend_max"]], "train": [m["train_from"], m["train_to"]]}
        notes.insert(0, f"Hệ số spend {m['b_log_spend']:.2f}: spend +10% thì đơn khoảng +{10 * m['b_log_spend']:.1f}% "
                        "(lợi suất giảm dần khi < 1). Học từ hiệu quả ads 8 tuần gần nhất: hiệu quả đổi thì kịch bản lệch. "
                        f"Backtest khi BIẾT spend thật: WAPE {m['backtest_wape_pct']}%, phủ ngoài mẫu ~"
                        f"{m['backtest_cover_pct']}%.")
    out["events_in_window"] = events
    if events:
        names = ", ".join(f"{e['event']} ({e['date']})" for e in events)
        notes.insert(0, f"Trong 14 ngày dự báo có sự kiện: {names}. Mô hình KHÔNG biết sự kiện (học từ ngày thường), "
                        "nên các ngày đó và vài ngày quanh đó có thể lệch xa khoảng"
                        + (", nhất là BFCM: chưa từng có ở quy mô này." if any(e["kind"] == "mua_sam" for e in events)
                           else "."))
    out["notes"] = notes
    return out


LOAD_STATUS_SQL = "select complete_through, latest_order_date, method from `{p}.gold.load_status`"


def last_complete_day() -> str:
    """Ngày đã trọn gần nhất theo Phoenix, để Claude biết 'hôm qua' là ngày nào."""
    from pipelines.dates import last_complete_day as done
    return str(done())


@server.tool(description="Hôm nay theo giờ Phoenix là ngày nào, ngày kinh doanh đã trọn gần nhất, và kho có số trọn "
                         "tới ngày nào (use_until = ngày nên tính tới). Gọi trước khi hiểu 'hôm qua', 'tuần trước'.")
def today_phoenix() -> dict:
    done = date.fromisoformat(last_complete_day())
    out = {"today_phoenix": str(done + timedelta(days=1)), "last_complete_day": str(done)}
    try:   # gold.load_status: kho có số TRỌN tới ngày nào (theo lúc nạp, 16/11)
        status = rows_of(LOAD_STATUS_SQL, {})[0]
        kho = date.fromisoformat(str(status["complete_through"]))
    except Exception:   # bảng chưa dựng (trước lần dbt build đầu có load_status): chỉ báo ngày theo đồng hồ
        out["note"] = "Ngày hôm nay chưa trọn, số còn thay đổi. Chưa đọc được gold.load_status."
        return out
    use = min(done, kho)
    out.update(data_complete_through=str(kho), use_until=str(use),
               note=("Ngày hôm nay chưa trọn, số còn thay đổi. "
                     + ("Kho đã có đủ tới hôm qua." if kho >= done else
                        f"Kho mới có số trọn tới {kho} (chưa nạp ngày sau): hỏi 'N ngày qua' thì tính tới {use}.")))
    return out


if __name__ == "__main__":
    server.run()
