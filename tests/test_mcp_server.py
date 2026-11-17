"""Kiểm MCP server bằng BigQuery giả: tool đăng ký đủ, ngày sai bị chặn bằng ToolError, MER tính từ tổng,
cảnh báo ngày thiếu Meta, định nghĩa đọc từ dbt. Không gọi BigQuery, không dùng khoá.

Chạy từ thư mục gốc:  python tests/test_mcp_server.py
"""

import asyncio
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from mcp_server import server as s  # noqa: E402

calls = []


def fake_query(sql, params):
    calls.append((sql, params))
    assert "{p}.gold.daily_performance" in sql and "@since" in sql and "@until" in sql, "chỉ đọc gold, có tham số"
    assert "{p}.gold.mart_daily_kpi" in sql or "count(*)" not in sql, "CM ước lấy từ mart_daily_kpi"
    assert "pii" not in sql
    if "count(*)" in sql:  # tổng
        return [{"days": 7, "days_with_meta": 7, "first_date": date(2026, 11, 1), "last_date": date(2026, 11, 7),
                 "orders": 815, "cancelled_orders": 3, "rev": Decimal("44370.74"), "spend": Decimal("24098.56"),
                 "mer": Decimal("1.8412"), "cpo": Decimal("29.57"), "meta_purchases": Decimal("700"),
                 "aov": Decimal("54.38"), "cm_est": Decimal("6127.92")}]
    return [{"date": date(2026, 2, 28), "orders": 20, "cancelled_orders": 0, "rev": Decimal("900.5"),
             "spend": None, "mer": None, "cpo": None, "meta_purchases": None, "meta_roas": None},
            {"date": date(2026, 3, 1), "orders": 25, "cancelled_orders": 1, "rev": Decimal("1100"),
             "spend": Decimal("100"), "mer": Decimal("11"), "cpo": Decimal("4"), "meta_purchases": Decimal("3"),
             "meta_roas": Decimal("2.5")}]


with patch.object(s, "query", fake_query):
    # 1. Tổng 1–7/11: đúng số đã kiểm trên gold, kiểu JSON đọc được
    out = s.performance_summary("2026-11-01", "2026-11-07")
    assert out["orders"] == 815 and out["rev"] == 44370.74 and out["mer"] == 1.8412, out
    assert out["aov"] == 54.38 and out["cm_est"] == 6127.92 and any("CM ước" in n for n in out["notes"]), out
    assert calls[-1][1] == {"since": date(2026, 11, 1), "until": date(2026, 11, 7)}
    assert len(out["notes"]) == 2, "đủ 7 ngày, đủ Meta thì chỉ 2 ghi chú chung (Meta, CM ước tạm)"
    # MER tổng phải tính từ tổng rev / tổng spend trong SQL, không lấy trung bình mer từng ngày
    assert "sum(spend)" in s.SUMMARY_SQL and "avg(mer)" not in s.SUMMARY_SQL

    # 2. Theo ngày: null giữ nguyên (ngày chưa có Meta), Decimal → số, date → chuỗi
    out = s.daily_performance("2026-02-28", "2026-03-01")
    assert out["rows"][0] == {"date": "2026-02-28", "orders": 20, "cancelled_orders": 0, "rev": 900.5, "spend": None,
                              "mer": None, "cpo": None, "meta_purchases": None, "meta_roas": None}, out["rows"][0]
    assert out["rows"][1]["mer"] == 11.0

    # 3. Ngày sai, đảo ngược, quá dài → ToolError (Claude thấy lý do)
    for bad in (("2026-13-01", "2026-13-02"), ("2026-11-07", "2026-11-01"), ("2024-01-01", "2026-11-01")):
        try:
            s.performance_summary(*bad)
        except ToolError:
            pass
        else:
            raise AssertionError(f"phải chặn {bad}")

# 4. Kho thiếu ngày, thiếu Meta → ghi chú rõ; kho không có ngày nào → ToolError
with patch.object(s, "query", lambda sql, p: [{"days": 3, "days_with_meta": 1, "first_date": date(2026, 2, 27),
                                               "last_date": date(2026, 3, 1), "orders": 60, "cancelled_orders": 0,
                                               "rev": Decimal("2000"), "spend": Decimal("100"), "mer": Decimal("11"),
                                               "cpo": Decimal("4"), "meta_purchases": Decimal("3")}]):
    notes = s.performance_summary("2026-02-26", "2026-03-01")["notes"]
    assert any("3/4 ngày" in n for n in notes) and any("2 ngày chưa có dữ liệu Meta" in n for n in notes), notes
with patch.object(s, "query", lambda sql, p: [{"days": 0}]):
    try:
        s.performance_summary("2020-01-01", "2020-01-02")
    except ToolError as error:
        assert "chưa có ngày nào" in str(error)
    else:
        raise AssertionError("không có ngày nào phải báo lỗi")

# 5. Định nghĩa đọc đúng từ dbt (_marts.yml), không viết lại lần hai
defs = s.metric_definitions()
assert defs["metrics"]["mer"]["formula"] == "rev / spend" and defs["timezone"] == "America/Phoenix", defs
assert defs["metrics"]["roas_type"]["source"] == "mart_type_day.roas" and defs["metrics"]["mer"]["traps"], defs

# 6. Đủ 4 tool đăng ký với MCP, gọi qua giao thức trả lỗi đúng dạng
names = {t.name for t in asyncio.run(s.server.list_tools())}
assert names == {"daily_performance", "performance_summary", "metric_definitions", "today_phoenix",
                 "type_performance", "product_performance", "ad_performance", "email_performance",
                 "customer_summary", "cohort_retention", "rfm_segments", "clv_summary", "product_abc", "anomaly_check", "forecast_orders"}, names
with patch.object(s, "query", fake_query):
    ok = asyncio.run(s.server.call_tool("performance_summary", {"since": "2026-11-01", "until": "2026-11-07"}))
    assert "815" in str(ok), ok
    try:  # MCPServer ném ToolError, lớp giao thức đổi thành isError gửi cho Claude kèm lý do
        asyncio.run(s.server.call_tool("performance_summary", {"since": "2026-11-07", "until": "2026-11-01"}))
    except ToolError as error:
        assert "phải trước hoặc bằng" in str(error)
    else:
        raise AssertionError("ngày đảo ngược phải báo lỗi qua giao thức")
with patch.object(s, "last_complete_day", lambda: "2026-11-15"):
    with patch.object(s, "query", lambda sql, params: [{"complete_through": date(2026, 11, 15),
                                                       "latest_order_date": date(2026, 11, 15), "method": "lúc nạp"}]):
        t = s.today_phoenix()
        assert t["today_phoenix"] == "2026-11-16" and t["use_until"] == "2026-11-15" and "đủ tới hôm qua" in t["note"], t
    with patch.object(s, "query", lambda sql, params: [{"complete_through": date(2026, 11, 13),
                                                       "latest_order_date": date(2026, 11, 14), "method": "lúc nạp"}]):
        t = s.today_phoenix()
        assert t["use_until"] == "2026-11-13" and "2026-11-13" in t["note"], "kho chưa nạp ngày 14, 15 thì tính tới 13"

    def no_table(sql, params):
        raise RuntimeError("Not found: Table datae-514203:gold.load_status")
    with patch.object(s, "query", no_table):
        t = s.today_phoenix()
        assert t["last_complete_day"] == "2026-11-15" and "use_until" not in t, "chưa có bảng thì vẫn trả ngày theo đồng hồ"

# 7. Tool mới (tuần 3): mỗi tool đọc đúng 1 bảng gold, giá trị Claude gửi đi bằng tham số có kiểu
seen = []


def fake_gold(sql, params):
    seen.append((sql, params))
    assert "pii" not in sql and "customer_key" not in sql.split("from")[0], "không đọc pii, không trả customer_key"
    templates = [s.TYPE_SQL, s.PRODUCT_SQL, s.EMAIL_SQL, s.CUSTOMER_SQL, s.COHORT_SQL, s.RFM_SQL, s.CLV_SQL,
                 s.ABC_SUMMARY_SQL, s.ABC_TOP_SQL, s.ABC_NEW_SQL, s.ABC_GINI_SQL, s.ABC_XYZ_SQL, s.ANOMALY_SQL] + \
                [s.AD_SQL.replace("{cols}", cols) for cols in s.AD_LEVELS.values()]
    assert sql in templates, "SQL phải đúng mẫu viết sẵn (giá trị Claude gửi không được ghép vào)"
    assert all(f"@{name}" in sql for name in params), "mọi giá trị đi bằng tham số @tên"
    if "mart_type_day" in sql:
        return [{"product_line": "Long Sleeve", "rev": Decimal("16204.38"), "spend": Decimal("10270.78"),
                 "roas": Decimal("1.58")},
                {"product_line": "Cardigan", "rev": Decimal("0"), "spend": Decimal("138.39"), "roas": Decimal("0")},
                {"product_line": "Can Cooler", "rev": Decimal("73.99"), "spend": Decimal("69.69"),
                 "roas": Decimal("1.06")},
                {"product_line": "(không rõ)", "rev": Decimal("54.43"), "spend": Decimal("0"), "roas": None},
                {"product_line": "(không theo type)", "rev": Decimal("0"), "spend": Decimal("96.91"),
                 "roas": Decimal("0")},
                {"product_line": "Sát ngưỡng", "rev": Decimal("146.55"), "spend": Decimal("100"),
                 "roas": Decimal("1.47")}]
    if "mart_anomaly_daily" in sql:
        def row(d, metric, level, score):
            return {"date": d, "weekday": "Tue", "event": None, "metric": metric, "method": "nhân theo thứ",
                    "value": Decimal("1"),
                    "expected": Decimal("1"), "pct_vs_expected": Decimal("0"), "score": Decimal(score),
                    "direction": "cao", "level": level, "last_date": date(2026, 11, 10)}
        out = [row(date(2026, 11, 10), m, "bình thường", "0.5") for m in
               ["orders", "gross_sales", "new_share", "cancel_rate", "refunds", "email_orders"]]
        out[0] = row(date(2026, 11, 10), "orders", "để ý", "-4.1")
        if params["span"] > 0:
            out += [row(date(2026, 11, 9), "cpo", "cần xử lý", "7.2"), row(date(2026, 11, 9), "mer", "để ý", "-3.6")]
        return out
    if "mart_xyz_group" in sql:
        return [{"cap_do": "dòng con", "nhom": "Performance Hoodie", "xyz_class": "Y", "cv": Decimal("0.928"),
                 "noise_cv": Decimal("0.174"), "trend_ratio": Decimal("8.06"), "first_sale_date": date(2026, 1, 3)}]
    if "mart_product_abc" in sql:
        if "abc_group" in sql:
            return [{"abc_group": g, "as_of_date": date(2026, 11, 11), "window_start": date(2026, 8, 14),
                     "products": n, "group_revenue": Decimal(rev), "avg_units": Decimal("1")}
                    for g, n, rev in [("D", 1021, "0"), ("A", 407, "248973.19"), ("Mới", 1819, "24831.09"),
                                      ("B", 474, "46599.11"), ("C", 458, "15525.49")]]
        if "gini_incl_dead" in sql:
            return [{"mature_products": 2360, "gini_incl_dead": Decimal("0.806")}]
        if "rev_per_live_day" in sql:
            return [{"product_title": "Mẫu mới", "rev_per_live_day": Decimal("12.5")}]
        return [{"product_title": "Mẫu A", "revenue": Decimal("5000"), "product_url": "https://thedeerly.com/products/x"}]
    if "mart_cohort_clv" in sql:
        base = {"cohort_size": 614, "month_spend": Decimal("16233.93"), "days_without_meta": 0}
        return [{**base, "cohort_month": "2026-04", "month_offset": 0, "avg_cum_rev": Decimal("61.35"),
                 "median_cum_rev": Decimal("45.99"), "ci_low": Decimal("58"), "ci_high": Decimal("64.7"),
                 "multiple_of_first": Decimal("1"), "is_complete": True},
                {**base, "cohort_month": "2026-04", "month_offset": 5, "avg_cum_rev": Decimal("71.40"),
                 "median_cum_rev": Decimal("45.99"), "ci_low": Decimal("66.83"), "ci_high": Decimal("75.98"),
                 "multiple_of_first": Decimal("1.164"), "is_complete": True},
                {"cohort_month": "2024-11", "cohort_size": 52, "month_spend": None, "days_without_meta": 30,
                 "month_offset": 0, "avg_cum_rev": Decimal("50"), "median_cum_rev": Decimal("45"),
                 "ci_low": Decimal("40"), "ci_high": Decimal("60"), "multiple_of_first": Decimal("1"),
                 "is_complete": True}]
    if "mart_rfm" in sql:
        return [{"segment": "Ngủ đông", "as_of_date": date(2026, 11, 11), "customers": 4128,
                 "pct_customers": Decimal("44.2"), "avg_recency_days": Decimal("131"),
                 "orders_per_customer": Decimal("1"), "avg_spend": Decimal("61.32"),
                 "revenue": Decimal("253129"), "pct_revenue": Decimal("37.6")},
                {"segment": "Có nguy cơ", "as_of_date": date(2026, 11, 11), "customers": 10,
                 "pct_customers": Decimal("0.1"), "avg_recency_days": Decimal("205"),
                 "orders_per_customer": Decimal("2"), "avg_spend": Decimal("67.09"),
                 "revenue": Decimal("670.9"), "pct_revenue": Decimal("0.1")}]
    if "mart_cohort_retention" in sql:
        return [{"cohort_month": "2026-02", "cohort_size": 15, "month_offset": 1, "active_customers": 2,
                 "retention_pct": 13.33, "ci_low": 3.74, "ci_high": 37.88, "is_complete": True},
                {"cohort_month": "2026-06", "cohort_size": 962, "month_offset": 1, "active_customers": 70,
                 "retention_pct": 7.28, "ci_low": 5.8, "ci_high": 9.1, "is_complete": True},
                {"cohort_month": "2026-06", "cohort_size": 962, "month_offset": 5, "active_customers": 9,
                 "retention_pct": 0.94, "ci_low": 0.5, "ci_high": 1.8, "is_complete": False}]
    if "dim_customer" in sql:
        return [{"cohort_month": "2026-09", "customers": 900, "repeat_pct": Decimal("8.1"),
                 "orders_per_customer": Decimal("1.1"), "avg_ltv": Decimal("60.5"), "aov": Decimal("55")},
                {"cohort_month": None, "customers": 900, "repeat_pct": Decimal("8.1"),
                 "orders_per_customer": Decimal("1.1"), "avg_ltv": Decimal("60.5"), "aov": Decimal("55")}]
    return [{"x": Decimal("1")}]


with patch.object(s, "query", fake_gold):
    out = s.type_performance("2026-11-04", "2026-11-10")
    assert "{p}.gold.mart_type_day" in seen[-1][0] and out["rows"][0]["roas"] == 1.58
    # '(không theo type)' (rev 0, roas 0) KHÔNG phải type lỗ; ROAS 1,4655 (in 1,47) vẫn dưới hoà vốn 1,4663
    assert out["breakeven_roas"] == 1.47 and out["below_breakeven"] == ["Cardigan", "Can Cooler", "Sát ngưỡng"], out
    assert out["below_breakeven_spend"] == 308.08 and out["untyped_spend"] == 96.91, out
    assert out["total"] == {"rev": 16479.35, "spend": 10675.77}, out
    assert any("ĐỦ" in n and "6 dòng" in n for n in out["notes"]), "phải dặn liệt kê đủ, không lược type nhỏ"
    assert "sum(rev), sum(spend)" in s.TYPE_SQL.replace("\n", " ") or "safe_divide(sum(rev), sum(spend))" in s.TYPE_SQL

    out = s.product_performance("2026-11-04", "2026-11-10", "Long Sleeve")
    assert any("CHƯA PHÂN ĐƯỢC" in n for n in out["notes"]), "dòng con trùng tên nhóm lớn phải được giải thích"
    assert "{p}.gold.product_daily" in seen[-1][0] and seen[-1][1]["product_line"] == "Long Sleeve"
    assert "@product_line" in seen[-1][0] and "Long Sleeve" not in seen[-1][0]
    s.product_performance("2026-11-04", "2026-11-10")
    assert seen[-1][1]["product_line"] == "", "để trống = mọi dòng"

    out = s.ad_performance("2026-11-04", "2026-11-10", "adset", 500)
    assert "{p}.gold.fct_ad_day" in seen[-1][0] and "adset_name" in seen[-1][0] and seen[-1][1]["top"] == 50
    assert seen[-1][1]["product_line"] == "" and seen[-1][1]["campaign"] == "" and out["truncated"] is False
    out = s.ad_performance("2026-11-04", "2026-11-10", "ad", 1, campaign="Static-Collection_AirPods Case")
    assert seen[-1][1]["campaign"] == "Static-Collection_AirPods Case" and "AirPods" not in seen[-1][0]
    assert out["truncated"] is True and any("chạm giới hạn 1 dòng" in n for n in out["notes"]), out
    s.ad_performance("2026-11-04", "2026-11-10", "ad", product_line="Phone Case")
    assert seen[-1][1]["product_line"] == "Phone Case" and "@product_line" in seen[-1][0]
    assert "{cols}" not in seen[-1][0] and "reach" not in seen[-1][0], "không cộng reach"
    for bad in ("campaign_name; drop table x", "creative"):
        try:
            s.ad_performance("2026-11-04", "2026-11-10", bad)
        except ToolError:
            pass
        else:
            raise AssertionError(f"level lạ phải bị chặn: {bad}")

    s.email_performance("2026-11-04", "2026-11-10", "flow")
    assert "{p}.gold.email_daily" in seen[-1][0] and seen[-1][1]["channel"] == "flow"
    assert "safe_divide(sum(opened), sum(received))" in s.EMAIL_SQL, "tỉ lệ mở từ tổng"
    try:
        s.email_performance("2026-11-04", "2026-11-10", "sms")
    except ToolError:
        pass
    else:
        raise AssertionError("channel lạ phải bị chặn")

    out = s.customer_summary("2026-09", "2026-09")
    assert "{p}.gold.dim_customer" in seen[-1][0] and out["rows"][-1]["cohort_month"] == "(tổng)"
    assert all("customer_key" not in row for row in out["rows"])
    for bad in (("2026-13", "2026-14"), ("2026-10", "2026-09"), ("09/2026", "2026-10")):
        try:
            s.customer_summary(*bad)
        except ToolError:
            pass
        else:
            raise AssertionError(f"tháng sai phải bị chặn: {bad}")

# 7b. Cohort: gom theo cohort, cờ cohort nhỏ (< 100 khách), max_offset bị chặn, tháng sai bị chặn
with patch.object(s, "query", fake_gold):
    out = s.cohort_retention("2026-01", "2026-10", 99)
    assert "{p}.gold.mart_cohort_retention" in seen[-1][0] and seen[-1][1]["max_offset"] == 24
    feb, jun = out["cohorts"]
    assert feb["small_cohort"] is True and jun["small_cohort"] is False and len(jun["months"]) == 2
    assert jun["months"][1] == {"k": 5, "retention_pct": 0.94, "ci_low": 0.5, "ci_high": 1.8,
                                "active_customers": 9, "complete": False}
    assert "2026-02" in out["notes"][0] and any("tháng LỊCH" in n for n in out["notes"]), out["notes"]
    assert any("KHÔNG chồng nhau" in n for n in out["notes"])
    assert s.cohort_retention("2026-06", "2026-06", 0)["max_offset"] == 1
    for bad in (("2026-13", "2026-14"), ("2026-10", "2026-09")):
        try:
            s.cohort_retention(*bad)
        except ToolError:
            pass
        else:
            raise AssertionError(f"tháng sai phải bị chặn: {bad}")

# 7c. RFM: chỉ số tổng theo nhóm, có luật gán nhóm, cờ nhóm nhỏ, không có customer_key
with patch.object(s, "query", fake_gold):
    out = s.rfm_segments()
    assert "{p}.gold.mart_rfm" in seen[-1][0] and seen[-1][1] == {}
    assert "customer_key" not in s.RFM_SQL and "group by segment" in s.RFM_SQL, "chỉ trả số tổng theo nhóm"
    assert out["as_of_date"] == "2026-11-11" and all("as_of_date" not in r for r in out["segments"])
    nd, cnc = out["segments"]
    assert nd["rule"].startswith("mua 1 lần") and nd["small_segment"] is False and cnc["small_segment"] is True
    assert "Có nguy cơ" in out["notes"][1] and any("Đã backtest" in n for n in out["notes"]), out["notes"]
    assert any("winback chỉ được tính phần vượt" in n for n in out["notes"]), "Ngủ đông có mức nền từ backtest"
    assert set(s.RFM_RULES) == {"Champions", "Loyal", "Mới quay lại", "Cần chú ý", "Khách mới", "Ngủ đông",
                                "Có nguy cơ", "Không thể để mất", "Đã mất"}, "đủ 9 nhóm như accepted_values"
with patch.object(s, "query", lambda sql, p: []):
    try:
        s.rfm_segments()
    except ToolError:
        pass
    else:
        raise AssertionError("bảng rỗng phải báo lỗi")

# 7d. CLV: CAC = spend tháng / số khách, tỉ lệ biên lấy từ dbt vars, tháng thiếu Meta không có CAC
with patch.object(s, "query", fake_gold):
    out = s.clv_summary("2024-11", "2026-04", 99)
    assert "{p}.gold.mart_cohort_clv" in seen[-1][0] and "{p}.gold.daily_performance" in seen[-1][0]
    assert seen[-1][1]["max_offset"] == 24 and out["margin_rate"] == 0.682
    apr, nov = out["cohorts"]
    assert apr["cac_new_customer"] == round(16233.93 / 614, 2) == 26.44, apr
    m5 = apr["months"][1]
    assert m5["clv_margin_est"] == round(71.40 * 0.682, 2) and m5["clv_margin_to_cac"] == round(m5["clv_margin_est"] / 26.44, 2)
    assert nov["cac_new_customer"] is None and nov["months"][0]["clv_margin_to_cac"] is None and nov["small_cohort"]
    assert "2024-11" in out["notes"][0] and any("Không tính được CAC" in n and "2024-11" in n for n in out["notes"])
    assert any("DOANH THU" in n for n in out["notes"]) and any("median_clv_rev" in n for n in out["notes"])
    for bad in (("2026-13", "2026-14"), ("2026-10", "2026-09")):
        try:
            s.clv_summary(*bad)
        except ToolError:
            pass
        else:
            raise AssertionError(f"tháng sai phải bị chặn: {bad}")

# 7e. ABC: % doanh thu tính trên mẫu đủ tuổi (A = 80%), thứ tự A..Mới, lọc dòng đi bằng tham số, top bị chặn
with patch.object(s, "query", fake_gold):
    out = s.product_abc("", 500)
    assert [g["abc_group"] for g in out["groups"]] == ["A", "B", "C", "D", "Mới"], out["groups"]
    a = out["groups"][0]
    assert a["pct_of_mature_revenue"] == 80.0 and a["pct_of_all_revenue"] == 74.1, a
    assert out["groups"][-1]["pct_of_mature_revenue"] is None, "Mới không tính % trên mẫu đủ tuổi"
    assert out["concentration"]["gini_incl_dead"] == 0.806 and out["as_of_date"] == "2026-11-11"
    top_call = [p for q, p in seen[-5:] if q == s.ABC_TOP_SQL]
    assert top_call == [{"product_line": "", "top": 50}], "top bị chặn 50"
    assert out["top_products"][0]["product_url"].startswith("https://") and out["top_new_products"]
    assert any("53% mẫu A vẫn A" in n for n in out["notes"]) and any("chưa nối ad" in n for n in out["notes"])
    assert out["xyz_by_group"][0]["trend_ratio"] == 8.06 and out["xyz_by_group"][0]["first_sale_date"] == "2026-01-03"
    assert any("trend_ratio" in n for n in out["notes"]) and any("KHÔNG đọc XYZ từng mẫu" in n for n in out["notes"])
    out = s.product_abc("Long Sleeve")
    assert all(p.get("product_line") == "Long Sleeve" for _, p in seen[-5:]), "lọc dòng đi bằng tham số"
    assert "Long Sleeve" not in s.ABC_SUMMARY_SQL and "abc_in_line" in out["notes"][0]
with patch.object(s, "query", lambda sql, p: []):
    try:
        s.product_abc("Không có dòng này")
    except ToolError as error:
        assert "đúng từng chữ" in str(error)
    else:
        raise AssertionError("dòng không có phải báo lỗi")

# 7f. anomaly_check: ngày cuối đủ chỉ số, báo động xếp nặng trước, ngày thiếu Meta được báo, tham số chặn
with patch.object(s, "query", fake_gold), patch.object(s, "last_complete_day", lambda: "2026-11-11"):
    out = s.anomaly_check()
    assert seen[-1][1] == {"until": "", "span": 0} and out["until"] == "2026-11-10"
    assert [a["metric"] for a in out["alerts"]] == ["orders"] and out["alerts"][0]["meaning"] == "thấp là xấu"
    assert any("Meta chưa nạp" in c for c in out["data_checks"]), out["data_checks"]
    assert any("nạp dở" in c and "2026-11-11" in c for c in out["data_checks"]), "bảng cũ hơn hôm qua phải báo, nêu lý do nạp dở"
    assert "last_date" not in out["latest_day"][0] and out["last_date_in_table"] == "2026-11-10"
    assert any("hoà vốn" in n and "1.47" in n for n in out["notes"]), "nêu MER hoà vốn 1,47 (Claude 2 lần nói MER 1,06 là hoà vốn)"
    out = s.anomaly_check("2026-11-10", 500)
    assert seen[-1][1] == {"until": "2026-11-10", "span": 30}, "days bị chặn 31"
    assert [a["level"] for a in out["alerts"]][0] == "cần xử lý", "cần xử lý xếp trước"
    assert not any("2026-11-11" in c for c in out["data_checks"]), "hỏi ngày cụ thể thì không so với hôm qua"
    assert "2026-11-10" not in s.ANOMALY_SQL
    for bad in ["10/11/2026", "hôm qua"]:
        try:
            s.anomaly_check(bad)
        except ToolError as error:
            assert "YYYY-MM-DD" in str(error)
        else:
            raise AssertionError("ngày sai phải báo lỗi")
with patch.object(s, "query", lambda sql, p: []):
    try:
        s.anomaly_check("2026-01-01")
    except ToolError as error:
        assert "mart_anomaly_daily" in str(error)
    else:
        raise AssertionError("không có dòng phải báo lỗi")

# 7g. forecast_orders: ETS + pacing khi tháng còn ≤ 14 ngày; kịch bản spend tính đúng công thức; ngoài khoảng spend
#     thì từ chối; dự báo cũ thì báo; SQL đúng mẫu, tham số @tên
def fake_fc(origin):
    def run(sql, params):
        seen.append((sql, params))
        assert sql in [s.FORECAST_SQL, s.SPEND_MODEL_SQL, s.MTD_SQL, s.EVENTS_SQL], "SQL phải đúng mẫu viết sẵn"
        assert all(f"@{name}" in sql for name in params)
        if "forecast_daily" in sql:
            return [{"origin": origin, "date": origin + timedelta(days=h), "h": h, "weekday": "Mon",
                     "fc": Decimal("100"), "lo": Decimal("80"), "hi": Decimal("125"), "k": Decimal("1.3"),
                     "train_from": date(2026, 8, 1), "train_to": origin, "backtest_wape_pct": Decimal("22.9"),
                     "backtest_cover_pct": Decimal("69.6"), "backtest_total_p80_pct": Decimal("15"),
                     "backtest_total_bias_pct": Decimal("-4")} for h in range(1, 15)]
        if "dim_event" in sql:
            cal = [(date(2026, 11, 26), "Thanksgiving", "le"), (date(2026, 11, 27), "Black Friday", "mua_sam")]
            return [{"date": d, "event": n, "kind": k} for d, n, k in cal if params["since"] <= d <= params["until"]]
        if "forecast_spend_model" in sql:
            return [{"origin": origin, "intercept": 0.0, "b_log_spend": 0.882, "dow_tue": 0.1, "dow_wed": 0.0,
                     "dow_thu": 0.0, "dow_fri": -0.1, "dow_sat": -0.2, "dow_sun": 0.05, "sigma": 0.2, "t80": 1.3,
                     "k": 1.28, "spend_min": 899.6, "spend_max": 3800.4, "spend_7d_mean": 3600.0, "n_days": 56,
                     "train_from": date(2026, 9, 16), "train_to": origin, "backtest_wape_pct": 20.5,
                     "backtest_cover_pct": 72.6, "backtest_total_p80_pct": 12.0, "backtest_total_bias_pct": -2.0}]
        return [{"orders": 2000, "days": params["until"].day}]
    return run


from datetime import timedelta  # noqa: E402

with patch.object(s, "query", fake_fc(date(2026, 11, 10))), patch.object(s, "last_complete_day", lambda: "2026-11-11"):
    out = s.forecast_orders()
    assert out["total_14d"] == 1400 and len(out["days"]) == 14 and out["data_checks"] == []
    assert out["total_14d_range"] == [1190, 1610], "khoảng tổng = ± p80 lệch tổng backtest (15%)"
    assert isinstance(out["pacing"], str) and "20 ngày" in out["pacing"], "tháng còn 20 ngày thì chưa đoán tổng tháng"
    assert any("NGOÀI MẪU" in n and "69.6" in n for n in out["notes"]) and any("Q4" in n for n in out["notes"])
    assert out["events_in_window"] == [], "11–24/11 không có sự kiện trong lịch giả"
    assert any("NẠP DỞ" in n and "2026-11-11" in n for n in out["notes"]), "ngày đầu dự báo có thể nạp dở (12/11: Claude so 92 đơn dở với 115)"
    out = s.forecast_orders(2000)
    import math  # noqa: E402
    d0 = out["days"][0]   # 11/11/2026 là thứ Tư: hệ số dow_wed = 0
    assert d0["weekday"] == "Wed" and abs(d0["orders"] - round(math.exp(0.882 * math.log(2000)), 1)) < 0.11, d0
    assert abs(d0["hi"] - round(math.exp(0.882 * math.log(2000) + 1.3 * 0.2 * 1.28), 1)) < 0.11, d0
    assert out["total_14d_range"] == s.total_range(out["total_14d"], 12.0)
    assert out["cpo_est"] == round(14 * 2000 / sum(d["orders"] for d in out["days"]), 2)
    assert any("+8.8%" in n for n in out["notes"]), "spend +10% → đơn +8,8%"
    for bad in [10000, 100]:
        try:
            s.forecast_orders(bad)
        except ToolError as error:
            assert "ngoài khoảng" in str(error) and "KHÔNG tự ngoại suy" in str(error)
        else:
            raise AssertionError("spend ngoài khoảng đã thấy phải từ chối")
    # số in trong lời từ chối phải tự dùng được (13/11: in "4,175" nhưng 4175 > spend_max 4174,6 bị từ chối)
    try:
        s.forecast_orders(10000)
    except ToolError as error:
        assert "(900–3,800 USD/ngày" in str(error) and "kịch bản ở 3,800 USD/ngày" in str(error), str(error)
    assert s.forecast_orders(3800)["total_14d"] > 0 and s.forecast_orders(900)["total_14d"] > 0
    try:   # quá THẤP: gợi ý mức thấp nhất, không khuyên tăng ngân sách
        s.forecast_orders(100)
    except ToolError as error:
        assert "kịch bản ở 900 USD/ngày" in str(error) and "tăng ngân sách" not in str(error), str(error)
with patch.object(s, "query", fake_fc(date(2026, 11, 20))), patch.object(s, "last_complete_day", lambda: "2026-11-21"):
    out = s.forecast_orders()
    pc = out["pacing"]
    assert [e["event"] for e in out["events_in_window"]] == ["Thanksgiving", "Black Friday"]
    assert "BFCM" in out["notes"][0] and "Black Friday (2026-11-27)" in out["notes"][0], out["notes"][0]
    assert pc["forecast_rest"] == 1000 and pc["month_total"] == 3000, pc   # 21–30/11 = 10 ngày × 100
    assert pc["month_total_range"] == [2800, 3250] and seen[-1][1]["month_start"] == date(2026, 11, 1)
with patch.object(s, "query", fake_fc(date(2026, 10, 25))), patch.object(s, "last_complete_day", lambda: "2026-11-11"):
    assert any("đã cũ 17 ngày" in c for c in s.forecast_orders()["data_checks"])
with patch.object(s, "query", lambda sql, p: []):
    try:
        s.forecast_orders()
    except ToolError as error:
        assert "forecast.publish" in str(error)
    else:
        raise AssertionError("bảng trống phải báo lỗi")

# 8. Sau GROUP BY (having, order by) không được có sum(<tên cột kết quả>): BigQuery hiểu là tổng của tổng,
#    lỗi "Aggregations of aggregations" (gặp 2 lần 12/11, lần 2 ở ad_performance chỉ lộ ra khi dry run).
import re  # noqa: E402

for sql in [s.DAILY_SQL, s.SUMMARY_SQL, s.TYPE_SQL, s.PRODUCT_SQL, s.EMAIL_SQL, s.CUSTOMER_SQL, s.COHORT_SQL, s.RFM_SQL, s.CLV_SQL,
            s.ABC_SUMMARY_SQL, s.ABC_TOP_SQL, s.ABC_NEW_SQL, s.ABC_GINI_SQL, s.ABC_XYZ_SQL, s.ANOMALY_SQL,
            s.FORECAST_SQL, s.SPEND_MODEL_SQL, s.MTD_SQL, s.EVENTS_SQL,
            s.AD_SQL.replace("{cols}", s.AD_LEVELS["campaign"])]:
    aliases = set(re.findall(r"\bas (\w+)", sql))
    tail = sql.lower().split("group by", 1)[1] if "group by" in sql.lower() else ""
    clash = [a for a in aliases if re.search(rf"\b(sum|avg|count|min|max)\(\s*{a}\s*\)", tail)]
    assert not clash, f"sau group by có tổng của cột kết quả {clash}"

# 8b. MCP always uses the verified read-only client and fails closed when absent.
import os  # noqa: E402
from pipelines import bq as bqmod  # noqa: E402
from dashboard import queries as dashboard_queries  # noqa: E402

with patch.object(dashboard_queries, "readonly_client", return_value="verified-readonly") as verified:
    with patch.dict(os.environ, {"MCP_CREDENTIALS": "synthetic-path"}):
        assert bqmod.mcp_client() == "verified-readonly"
        verified.assert_called_once()
with patch.object(bqmod, "client", side_effect=AssertionError("must never use pipeline")):
    with patch.dict(os.environ, {"MCP_CREDENTIALS": ""}):
        try:
            bqmod.mcp_client()
        except RuntimeError:
            pass
        else:
            raise AssertionError("missing read-only key must fail closed")
assert "mcp_client()" in open(ROOT / "mcp_server" / "server.py", encoding="utf-8").read()

# 9. Kiểu tham số gửi BigQuery: ngày DATE, số INT64, chữ STRING
assert (s.param_type(date(2026, 11, 1)), s.param_type(20), s.param_type("flow")) == ("DATE", "INT64", "STRING")

print("PASS: MCP 15 tool, chỉ đọc gold có tham số, MER/ROAS/tỉ lệ mở từ tổng, null Meta giữ nguyên, "
      "ngày/level/channel/tháng sai báo ToolError, không trả customer_key, định nghĩa từ metrics.yml")
