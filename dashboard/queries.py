"""Câu SQL đọc gold cho dashboard React (backend webapp/api). Một chỗ định nghĩa cho mỗi câu.

Quy tắc: chỉ khoá CHỈ ĐỌC datae-mcp; mọi giá trị đi bằng tham số @tên (kiểu DATE); ≤ 50 MB mỗi câu.
"""

import json
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 50 * 1024 * 1024


class ReadOnlyKeyError(RuntimeError):
    """Thiếu khoá datae-mcp hoặc khoá không phải chỉ đọc."""


def readonly_client():
    """Client BigQuery bằng khoá datae-mcp. Thiếu khoá hoặc khoá không phải datae-mcp thì báo lỗi, KHÔNG dùng tạm
    khoá pipeline (quyền ghi)."""
    from dotenv import load_dotenv

    from pipelines.bq import MCP_KEY_ENV, client, settings

    load_dotenv(ROOT / ".env")
    if not os.environ.get(MCP_KEY_ENV, "").strip():
        raise ReadOnlyKeyError(f"Chưa có {MCP_KEY_ENV} trong .env. Dashboard chỉ chạy bằng khoá chỉ đọc datae-mcp.")
    _, key_path, _ = settings(MCP_KEY_ENV)
    email = json.loads(Path(key_path).read_text(encoding="utf-8")).get("client_email", "")
    if not email.startswith("datae-mcp@"):
        raise ReadOnlyKeyError(f"{MCP_KEY_ENV} phải là khoá datae-mcp (chỉ đọc).")
    return client(MCP_KEY_ENV)


def run(c, sql: str, params: dict | None = None) -> pd.DataFrame:
    from google.cloud import bigquery

    cfg = bigquery.QueryJobConfig(
        maximum_bytes_billed=MAX_BYTES,
        query_parameters=[bigquery.ScalarQueryParameter(k, "DATE", v) for k, v in (params or {}).items()])
    rows = [dict(r) for r in c.query(sql.format(p=c.project), job_config=cfg).result()]
    df = pd.DataFrame(rows)
    for col in df.columns:   # NUMERIC về float để tính và vẽ
        if df[col].dtype == object and len(df) and df[col].map(lambda v: hasattr(v, "as_tuple")).any():
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# Bảng gold mà dashboard đọc: thời điểm sửa cuối của chúng là "phiên bản dữ liệu" (dbt build, forecast.publish).
GOLD_TABLES = ["fct_orders", "mart_daily_kpi", "mart_type_day", "fct_ad_day", "product_daily", "mart_product_abc",
               "fct_lines", "dim_product", "mart_repeat_60d", "mart_rfm", "mart_cohort_retention", "daily_performance",
               "email_daily", "mart_anomaly_daily", "forecast_daily", "load_status", "mart_cohort_clv"]


def data_version(c) -> str:
    """Lần sửa cuối của các bảng gold (đọc metadata, không tốn truy vấn). Đổi = vừa nạp/build lại."""
    from concurrent.futures import ThreadPoolExecutor

    # hỏi song song: lần lượt 15 bảng mất ~15 giây (16/11), song song ~1–2 giây
    from google.api_core.exceptions import NotFound

    def modified(t):
        try:
            return c.get_table(f"{c.project}.gold.{t}").modified
        except NotFound:   # bảng mới (load_status) chưa dựng: bỏ qua, không làm hỏng cả trang
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        stamps = [s for s in pool.map(modified, GOLD_TABLES) if s is not None]
    return max(stamps).isoformat()


LATEST_LOADED = "select max(order_date) as d from `{p}.gold.fct_orders`"
# Ngày đã trọn của kho theo LÚC NẠP (macro complete_through, 16/11). Chưa có bảng thì pages.context lùi về
# LATEST_LOADED − 1 như cũ.
LOAD_STATUS = "select complete_through as d from `{p}.gold.load_status`"

DAILY_KPI = """select date, rev, orders, spend, mer, cpo, cm_est from `{p}.gold.mart_daily_kpi`
where date between @since and @until order by date"""

TYPE_ROAS = """
select product_line, sum(rev) as rev, if(countif(spend is null) > 0, null, sum(spend)) as spend
from `{p}.gold.mart_type_day` where date between @since and @until
group by 1 order by spend desc, rev desc"""

CAMPAIGNS = """
select campaign_name, ad_product_line, sum(spend) as spend, sum(impressions) as impressions,
       sum(inline_link_clicks) as link_clicks, sum(meta_purchases) as meta_purchases,
       sum(meta_purchase_value) as meta_purchase_value
from `{p}.gold.fct_ad_day` where date between @since and @until
group by 1, 2 order by spend desc limit 1001"""

FUNNEL = """
select sum(impressions) as impressions, sum(inline_link_clicks) as link_clicks,
       sum(meta_view_content) as view_content, sum(meta_add_to_cart) as add_to_cart,
       sum(meta_initiate_checkout) as checkout, sum(meta_purchases) as purchases
from `{p}.gold.fct_ad_day` where date between @since and @until"""

ABC = """
select product_title, product_line, abc_class, revenue, share_pct, units, rank_all, is_new,
       window_start, as_of_date
from `{p}.gold.mart_product_abc`"""

SPECIES = """
select coalesce(p.species, '(không có species)') as species,
       sum(if(l.order_date between @since and @until, l.line_revenue, 0)) as rev,
       sum(if(l.order_date between @p_since and @p_until, l.line_revenue, 0)) as rev_truoc
from `{p}.gold.fct_lines` l left join `{p}.gold.dim_product` p using (product_id)
where l.order_date between @p_since and @until
group by 1"""

CUSTOMERS_WEEKLY = """
select date_trunc(order_date, week(sunday)) as tuan,
       countif(is_first_order) as khach_moi, countif(not is_first_order and customer_key is not null) as khach_cu,
       countif(customer_key is null) as khong_email
from `{p}.gold.fct_orders` where order_date between @since and @until
group by 1"""

REPEAT_BY_TYPE = """
select first_type, countif(is_eligible) as khach, countif(repeat_60d) as mua_lan_2, any_value(as_of_date) as as_of
from `{p}.gold.mart_repeat_60d` group by 1 having countif(is_eligible) > 0 order by khach desc"""

RFM = """
select segment, count(*) as khach, sum(monetary) as doanh_thu, any_value(as_of_date) as as_of
from `{p}.gold.mart_rfm` group by 1"""

COHORT = """
select cohort_month, month_offset, cohort_size, retention_pct, is_complete
from `{p}.gold.mart_cohort_retention`
where cohort_month >= format_date('%Y-%m', date_sub(current_date('America/Phoenix'), interval 12 month))
  and month_offset between 1 and 6"""

EMAIL_WEEKLY = """
with r as (
  select date_trunc(date, week(sunday)) as tuan, sum(rev) as rev
  from `{p}.gold.daily_performance` where date between @since and @until group by 1),
e as (
  select date_trunc(date, week(sunday)) as tuan,
         sum(if(channel = 'campaign', placed_value, 0)) as campaign,
         sum(if(channel = 'flow', placed_value, 0)) as flow
  from `{p}.gold.email_daily` where date between @since and @until group by 1)
select r.tuan, r.rev, e.campaign, e.flow
from r left join e using (tuan)"""

ALERTS = """
select date, weekday, event, metric, value, expected, pct_vs_expected, score, direction, level
from `{p}.gold.mart_anomaly_daily`
where date between @since and @until and level in ('để ý', 'cần xử lý')
order by date desc, abs(score) desc"""

FORECAST = """
select date, fc, lo, hi, backtest_total_p80_pct, backtest_total_bias_pct, origin
from `{p}.gold.forecast_daily` order by date"""

ORDERS_DAILY = """select date, orders from `{p}.gold.daily_performance` where date between @since and @until
order by date"""

# Hoàn tiền theo NGÀY HOÀN (khớp mart_anomaly_daily, trang Cảnh báo): tiền từ daily_performance.refunds,
# số đơn = đơn có lần hoàn ĐẦU TIÊN trong kỳ (fct_orders.first_refund_date). Kỳ này và kỳ trước trong 1 câu.
REFUNDS = """
select
  (select sum(refunds) from `{p}.gold.daily_performance` where date between @since and @until)     as amount,
  (select sum(refunds) from `{p}.gold.daily_performance` where date between @p_since and @p_until) as p_amount,
  (select count(*) from `{p}.gold.fct_orders` where first_refund_date between @since and @until)     as orders,
  (select count(*) from `{p}.gold.fct_orders` where first_refund_date between @p_since and @p_until) as p_orders"""

# Hoàn trả theo dòng sản phẩm, theo NGÀY ĐẶT của đơn: cái hoàn = quantity − current_quantity, tiền hoàn =
# line_gross_after_discounts − line_revenue. Không gồm hoàn ship / hoàn một phần không gắn dòng (nên nhỏ hơn REFUNDS).
RETURNS_BY_LINE = """
select product_line, sum(quantity) as sold, sum(quantity - current_quantity) as returned,
       sum(line_gross_after_discounts - line_revenue) as returned_value
from `{p}.gold.fct_lines` where order_date between @since and @until
group by 1 having sum(quantity) > 0 order by returned_value desc, sold desc"""

RETURNS_TOP = """
select product_title, product_line, sum(quantity) as sold, sum(quantity - current_quantity) as returned,
       sum(line_gross_after_discounts - line_revenue) as returned_value
from `{p}.gold.fct_lines` where order_date between @since and @until
group by 1, 2 having sum(quantity - current_quantity) > 0 order by returned_value desc limit 5"""

# Aggregate exploration; never expose order/customer identifiers.
PRODUCTS = """
select product_title, product_line, sum(line_revenue) as revenue,
       sum(current_quantity) as units, sum(quantity - current_quantity) as returned
from `{p}.gold.fct_lines` where order_date between @since and @until
group by 1, 2 order by revenue desc limit 1001"""
CLV = """select cohort_month, month_offset, cohort_size, avg_cum_rev, median_cum_rev,
ci_low, ci_high, multiple_of_first, is_complete from `{p}.gold.mart_cohort_clv`
where month_offset between 0 and 6 order by cohort_month desc, month_offset"""
HEALTH = """select 'Shopify orders' as source, min(order_date) as first_date, max(order_date) as last_date,
count(distinct order_date) as observed_days from `{p}.gold.fct_orders` where order_date <= @until
union all select 'Meta ads', min(date), max(date), count(distinct date)
from `{p}.gold.fct_ad_day` where date <= @until
union all select 'Klaviyo email', min(date), max(date), count(distinct date)
from `{p}.gold.email_daily` where date <= @until"""
LOAD_EVIDENCE = "select complete_through, method, built_at from `{p}.gold.load_status`"
