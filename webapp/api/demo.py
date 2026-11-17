"""Deterministic synthetic warehouse adapter. No credentials, network, or SQL engine.
Uses the SAME queries -> DataFrame -> pages -> JSON contracts as live mode.
Only the published example report SQL is accepted; arbitrary SQL is never simulated.
"""

from datetime import date, timedelta
import pandas as pd
from decimal import Decimal, ROUND_HALF_UP
from dashboard import queries as q
from dashboard import kpi

END = date(2026, 11, 15)
VERSION = "2026-11-16T07:15:00+00:00"
SPEC = {
    "title": "Doanh thu & chi phí · 14 ngày",
    "chart": "line",
    "x": "date",
    "y": ["rev", "spend"],
    "note": "Dữ liệu tổng hợp giả lập. Biểu đồ cập nhật theo nguồn demo.",
    "sql": "select date, rev, spend from `demo.gold.mart_daily_kpi` where date between date_sub((select complete_through from `demo.gold.load_status`), interval 13 day) and (select complete_through from `demo.gold.load_status`) order by date",
}
LINES = ["Long Sleeve", "Phone Case", "Hoodie", "Ornament", "AirPods Case"]


def daily(a, b):
    cogs, fee = kpi.rates()
    rows = []
    for i in range((b - a).days + 1):
        d = a + timedelta(days=i)
        n = (d - date(2026, 1, 1)).days
        orders = 72 + (n * 7) % 39
        rev = round(orders * (45 + (n % 5) * 1.25), 2)
        spend = round(1900 + (n * 83) % 900, 2)
        rows.append(
            dict(
                date=d,
                orders=orders,
                rev=rev,
                spend=spend,
                mer=rev / spend,
                cpo=spend / orders,
                cm_est=float(
                    (
                        Decimal(str(rev)) * (1 - Decimal(str(cogs)) - Decimal(str(fee)))
                        - Decimal(str(spend))
                    ).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
                ),
            )
        )
    return rows


def product_rows(a, b):
    total = round(sum(r["rev"] for r in daily(a, b)) * 0.89, 2)
    weights = [1 / (i + 3) for i in range(25)]
    denom = sum(weights)
    rows = []
    for i, w in enumerate(weights):
        revenue = round(total * w / denom, 2)
        if i == 24:
            revenue = round(total - sum(r["revenue"] for r in rows), 2)
        rows.append(
            dict(
                product_title=f"{['Heron at Dawn', 'Quiet Pines', 'Wildflower Meadow', 'Coastal Flight', 'Moonlit Garden'][i % 5]} · {i + 1:02}",
                product_line=LINES[i % 5],
                revenue=revenue,
                units=round(revenue / 32),
                returned=2 if i % 6 == 0 else 0,
                abc_class="A" if i < 7 else "B" if i < 15 else "C",
                share_pct=round(100 * revenue / total, 2),
                rank_all=i + 1,
                is_new=False,
                window_start=a,
                as_of_date=b,
            )
        )
    cumulative = 0
    for row in rows:
        row["abc_class"] = (
            "A"
            if cumulative / total < 0.8
            else "B"
            if cumulative / total < 0.95
            else "C"
        )
        cumulative += row["revenue"]
    return rows


def campaign_rows(a, b):
    total = round(sum(r["spend"] for r in daily(a, b)), 2)
    weights = [1 / (i + 2) for i in range(20)]
    denom = sum(weights)
    rows = []
    for i, w in enumerate(weights):
        spend = round(total * w / denom, 2)
        if i == 19:
            spend = round(total - sum(r["spend"] for r in rows), 2)
        rows.append(
            dict(
                campaign_name=f"Catalog · {LINES[i % 5]} · Design {i + 1:02}",
                ad_product_line=LINES[i % 5],
                spend=spend,
                impressions=80000 - i * 2700,
                link_clicks=1800 - i * 53,
                meta_purchases=55 - i,
                meta_purchase_value=round(spend * (1.4 + i % 5 * 0.2), 2),
            )
        )
    return rows


def refunds(a, b):
    amounts = [
        15 + ((a + timedelta(days=i) - date(2026, 1, 1)).days % 4) * 3.5
        for i in range((b - a).days + 1)
        if (a + timedelta(days=i) - date(2026, 1, 1)).days % 7 == 2
    ]
    return round(sum(amounts), 2), len(amounts)


def fetch(sql, params):
    p = params or {}
    a = p.get("since", END - timedelta(days=89))
    b = p.get("until", END)
    rows = []
    if sql in (q.LOAD_STATUS, q.LATEST_LOADED):
        rows = [{"d": END}]
    elif sql == q.LOAD_EVIDENCE:
        rows = [
            dict(complete_through=END, method="lúc nạp · giả lập", built_at=VERSION)
        ]
    elif sql == q.HEALTH:
        rows = [
            dict(
                source=s, first_date=date(2026, 1, 1), last_date=END, observed_days=319
            )
            for s in ["Shopify orders", "Meta ads", "Klaviyo email"]
        ]
    elif sql in (q.DAILY_KPI, q.ORDERS_DAILY):
        rows = daily(a, b)
    elif sql == q.REFUNDS:
        amount, orders = refunds(a, b)
        previous, porders = refunds(p["p_since"], p["p_until"])
        rows = [dict(amount=amount, orders=orders, p_amount=previous, p_orders=porders)]
    elif sql == q.TYPE_ROAS:
        products = product_rows(a, b)
        campaigns = campaign_rows(a, b)
        rows = [
            dict(
                product_line=l,
                rev=round(
                    sum(r["revenue"] for r in products if r["product_line"] == l), 2
                ),
                spend=round(
                    sum(r["spend"] for r in campaigns if r["ad_product_line"] == l), 2
                ),
            )
            for l in LINES
        ]
    elif sql == q.CAMPAIGNS:
        rows = campaign_rows(a, b)
    elif sql == q.FUNNEL:
        campaigns = campaign_rows(a, b)
        rows = [
            dict(
                impressions=sum(c["impressions"] for c in campaigns),
                link_clicks=sum(c["link_clicks"] for c in campaigns),
                view_content=35000,
                add_to_cart=3300,
                checkout=1900,
                purchases=sum(c["meta_purchases"] for c in campaigns),
            )
        ]
    elif sql == q.PRODUCTS:
        rows = product_rows(a, b)
    elif sql == q.ABC:
        rows = product_rows(END - timedelta(days=89), END)
    elif sql == q.SPECIES:
        total = sum(r["revenue"] for r in product_rows(a, b))
        prior = sum(r["revenue"] for r in product_rows(p["p_since"], p["p_until"]))
        rows = [
            dict(species=l, rev=round(total * w, 2), rev_truoc=round(prior * w, 2))
            for l, w in zip(
                [
                    "Heron",
                    "Cardinal",
                    "Hummingbird",
                    "Owl",
                    "Fox",
                    "(không có species)",
                ],
                [0.25, 0.2, 0.15, 0.1, 0.1, 0.2],
            )
        ]
    elif sql in (q.RETURNS_BY_LINE, q.RETURNS_TOP):
        products = product_rows(a, b)
        if sql == q.RETURNS_BY_LINE:
            rows = [
                dict(
                    product_line=l,
                    sold=sum(
                        r["units"] + r["returned"]
                        for r in products
                        if r["product_line"] == l
                    ),
                    returned=sum(
                        r["returned"] for r in products if r["product_line"] == l
                    ),
                    returned_value=26
                    * sum(r["returned"] for r in products if r["product_line"] == l),
                )
                for l in LINES
            ]
        else:
            rows = [
                dict(
                    product_title=r["product_title"],
                    product_line=r["product_line"],
                    sold=r["units"] + r["returned"],
                    returned=r["returned"],
                    returned_value=r["returned"] * 26,
                )
                for r in products
                if r["returned"]
            ][:5]
    elif sql in (q.CUSTOMERS_WEEKLY, q.EMAIL_WEEKLY):
        for i in range(12):
            week = a + timedelta(days=i * 7)
            days = daily(week, week + timedelta(days=6))
            rev = round(sum(r["rev"] for r in days), 2)
            orders = sum(r["orders"] for r in days)
            new = round(orders * 0.84)
            rows.append(
                dict(
                    tuan=week,
                    khach_moi=new,
                    khach_cu=orders - new - 4,
                    khong_email=4,
                    rev=rev,
                    campaign=round(rev * 0.03, 2),
                    flow=round(rev * 0.08, 2),
                )
            )
    elif sql == q.REPEAT_BY_TYPE:
        rows = [
            dict(first_type=l, khach=600 - i * 73, mua_lan_2=65 - i * 8, as_of=END)
            for i, l in enumerate(LINES)
        ]
    elif sql == q.RFM:
        from webapp.api.pages import RFM_ORDER

        rows = [
            dict(segment=l, khach=900 - i * 75, doanh_thu=48000 - i * 4600, as_of=END)
            for i, l in enumerate(RFM_ORDER)
        ]
    elif sql in (q.COHORT, q.CLV):
        for m in range(4, 12):
            for k in range(0 if sql == q.CLV else 1, min(6, 11 - m) + 1):
                rows.append(
                    dict(
                        cohort_month=f"2026-{m:02}",
                        month_offset=k,
                        cohort_size=400 + m * 51,
                        retention_pct=round(8 - k * 0.7 + (m % 3) * 0.2, 2),
                        is_complete=m + k < 11,
                        avg_cum_rev=round(49 + k * 3.2, 2),
                        median_cum_rev=44 + k,
                        ci_low=46 + k * 3,
                        ci_high=52 + k * 3.4,
                        multiple_of_first=round((49 + k * 3.2) / 49, 3),
                    )
                )
    elif sql == q.ALERTS:
        rows = [
            dict(
                date=END - timedelta(days=1),
                weekday="Sat",
                event=None,
                metric="refunds",
                value=refunds(END - timedelta(days=1), END - timedelta(days=1))[0],
                expected=6,
                pct_vs_expected=208.33,
                score=4.1,
                direction="cao",
                level="để ý",
            )
        ]
    elif sql == q.FORECAST:
        rows = [
            dict(
                date=END + timedelta(days=i),
                fc=97 + i % 7 * 3,
                lo=65 + i % 7 * 2,
                hi=137 + i % 7 * 4,
                backtest_total_p80_pct=32.6,
                backtest_total_bias_pct=-4,
                origin=END,
            )
            for i in range(1, 15)
        ]
    else:
        raise ValueError("Demo không hỗ trợ truy vấn này.")
    return pd.DataFrame(rows)


def run_report(spec):
    from webapp.api import reports, pages

    spec = reports.check_spec(spec)
    reports.check_sql_text(spec["sql"])
    if spec["sql"] != SPEC["sql"]:
        raise reports.ReportError(
            "Demo chỉ chạy SQL mẫu công bố; không mô phỏng SQL tùy ý. Dùng “Tạo biểu đồ mẫu”."
        )
    rows = [
        {k: r[k] for k in ("date", "rev", "spend")}
        for r in daily(END - timedelta(days=13), END)
    ]
    columns = ["date", "rev", "spend"]
    reports.validate_chart_data(spec, columns, pages.clean(rows))
    return dict(columns=columns, rows=pages.clean(rows), truncated=False)


def ask(message):
    from webapp.api.pages import clean

    t = kpi.totals(daily(END - timedelta(days=6), END))
    yield {"t": "tool", "name": "Demo · tổng hợp fixture cục bộ"}
    yield {
        "t": "done",
        "text": f"**Phân tích mẫu · dữ liệu giả lập, không gọi Claude.**\n\nKỳ 09–15/11/2026 (America/Phoenix): {t['orders']} đơn, doanh thu {t['rev']:,.2f} USD, MER {t['mer']:.2f}. MER tính từ tổng doanh thu / tổng spend.\n\nĐây là phản hồi cố định để thử lưu và mở lại phân tích; không phải câu trả lời AI cho câu hỏi tùy ý. CM dùng giá vốn tạm; doanh thu đã trừ hoàn, không trừ hoàn lần nữa. Biểu đồ dưới đây dùng 14 ngày fixture.",
        "reports": [SPEC],
        "report_errors": [],
    }
