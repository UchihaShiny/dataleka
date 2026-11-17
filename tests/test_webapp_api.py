"""Kiểm backend dashboard React (webapp/api) bằng dữ liệu giả: không gọi BigQuery, không dùng khoá.

Chạy từ thư mục gốc:  python tests/test_webapp_api.py
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from dashboard import queries as q  # noqa: E402
from webapp.api import pages  # noqa: E402

KPI = [(5, 4567.60, 93, 3409.53, -294.43), (6, 6046.35, 98, 3336.44, 787.17), (7, 6366.77, 128, 3435.71, 906.43),
       (8, 6650.68, 112, 3453.74, 1082.02), (9, 6475.77, 121, 3143.38, 1273.10),
       (10, 6281.82, 126, 3744.46, 539.74), (11, 7857.91, 124, 3601.02, 1758.07)]
seen = []


def fake(sql, params):
    seen.append((sql, params))
    assert "{p}.gold." in sql and (params is None or all(isinstance(v, date) for v in params.values()))
    if sql == q.LATEST_LOADED:
        return pd.DataFrame([{"d": date(2026, 11, 12)}])
    if sql == q.DAILY_KPI:
        rows = [{"date": date(2026, 11, d), "rev": r, "orders": o, "spend": s, "mer": r / s, "cpo": s / o, "cm_est": c}
                for d, r, o, s, c in KPI]
        return pd.DataFrame([x for x in rows if params["since"] <= x["date"] <= params["until"]])
    if sql == q.TYPE_ROAS:
        return pd.DataFrame([{"product_line": "Long Sleeve", "rev": 17601.25, "spend": 11175.31},
                             {"product_line": "Can Cooler", "rev": 73.99, "spend": 69.69},
                             {"product_line": "(không theo type)", "rev": 0.0, "spend": 96.91}])
    if sql == q.CAMPAIGNS:
        return pd.DataFrame([{"campaign_name": "Catalog-PDP_Phone Case_Theme", "ad_product_line": "Phone Case",
                              "spend": 1000.0, "impressions": 100000, "link_clicks": 1500, "meta_purchases": 30,
                              "meta_purchase_value": 1800.0}])
    if sql == q.FUNNEL:
        return pd.DataFrame([{"impressions": 1000, "link_clicks": 20, "view_content": 30, "add_to_cart": 6,
                              "checkout": 3, "purchases": 2}])
    if sql == q.FORECAST:
        return pd.DataFrame([{"date": date(2026, 11, 12 + i), "fc": 132.2, "lo": 90.0, "hi": 180.0,
                              "backtest_total_p80_pct": 32.6, "backtest_total_bias_pct": -4.0,
                              "origin": date(2026, 11, 11)} for i in range(14)])
    if sql == q.ORDERS_DAILY:
        return pd.DataFrame([{"date": date(2026, 11, 1), "orders": 100}, {"date": date(2026, 11, 2), "orders": float("nan")}])
    if sql == q.ALERTS:
        return pd.DataFrame([{"date": date(2026, 11, 11), "weekday": "Wed", "event": "Veterans Day",
                              "metric": "gross_sales", "value": 7857.91, "expected": 5148.3, "pct_vs_expected": 52.6,
                              "score": 3.78, "direction": "cao", "level": "để ý"}])
    if sql == q.REFUNDS:   # kỳ trước không có hoàn: sum rỗng = NaN
        return pd.DataFrame([{"amount": 217.97, "p_amount": float("nan"), "orders": 3, "p_orders": 0}])
    if sql == q.RETURNS_BY_LINE:
        return pd.DataFrame([{"product_line": "Long Sleeve", "sold": 2312, "returned": 10, "returned_value": 329.42},
                             {"product_line": "AirPods Case", "sold": 52, "returned": 1, "returned_value": 25.99}])
    if sql == q.RETURNS_TOP:
        return pd.DataFrame([{"product_title": "Mẫu A", "product_line": "Long Sleeve", "sold": 40, "returned": 2,
                              "returned_value": 70.0}])
    return pd.DataFrame()


def test_hoan_tien_tong_quan_va_san_pham():
    ctx = pages.context(fake, date(2026, 11, 11), "7")
    rf = pages.overview(fake, ctx)["refunds"]
    assert rf["amount"] == 217.97 and rf["orders"] == 3 and rf["p_amount"] is None, rf
    assert round(rf["pct_of_rev"], 2) == round(100 * 217.97 / 44246.90, 2)
    assert rf["change"] is None, "kỳ trước thiếu ngày thì không so"
    assert any(s == q.REFUNDS and p["since"] == date(2026, 11, 5) and p["p_until"] == date(2026, 11, 4)
               for s, p in seen), "kỳ này 5–11/11, kỳ trước tới 4/11"
    ret = pages.products(fake, ctx)["returns"]
    assert ret["sold"] == 2364 and ret["returned"] == 11 and round(ret["value"], 2) == 355.41, ret
    assert round(ret["pct"], 3) == round(100 * 11 / 2364, 3)
    assert [x["product_line"] for x in ret["lines"]] == ["Long Sleeve", "AirPods Case"]
    assert round(ret["lines"][1]["return_pct"], 2) == 1.92 and ret["top"][0]["return_pct"] == 5.0


def test_ngay_tron_theo_luc_nap():
    from google.api_core.exceptions import NotFound

    # nạp 00:07 Phoenix 16/11: kho có đơn tới 15/11 (đã trọn), load_status ghi 15/11 → dashboard tới 15/11
    def loaded_after_midnight(sql, params):
        if sql == q.LOAD_STATUS:
            return pd.DataFrame([{"d": date(2026, 11, 15)}])
        if sql == q.LATEST_LOADED:
            return pd.DataFrame([{"d": date(2026, 11, 15)}])
        return fake(sql, params)
    assert pages.context(loaded_after_midnight, date(2026, 11, 15), "7")["end_max"] == date(2026, 11, 15)
    # đồng hồ mới tới 14/11 thì không vượt đồng hồ
    assert pages.context(loaded_after_midnight, date(2026, 11, 14), "7")["end_max"] == date(2026, 11, 14)

    # chưa dựng load_status (trước lần dbt build đầu): đoán như cũ = ngày mới nhất có đơn − 1
    def no_table(sql, params):
        if sql == q.LOAD_STATUS:
            raise NotFound("Not found: Table gold.load_status")
        return fake(sql, params)
    assert pages.context(no_table, date(2026, 11, 12), "7")["end_max"] == date(2026, 11, 11)


def test_context_skips_partial_day():
    ctx = pages.context(fake, date(2026, 11, 11), "7")
    assert ctx["end_max"] == date(2026, 11, 11) and ctx["start"] == date(2026, 11, 5), ctx
    assert pages.context(fake, date(2026, 11, 11), "month")["start"] == date(2026, 11, 1)


def test_overview_matches_answer_q1():
    ctx = pages.context(fake, date(2026, 11, 11), "7")
    out = pages.overview(fake, ctx)
    t = out["totals"]
    assert round(t["rev"], 2) == 44246.90 and t["orders"] == 802 and round(t["mer"], 2) == 1.83, t
    assert round(t["cm_est"], 2) == 6052.10
    assert out["comparable"] is False and out["change"]["rev"] is None, "kỳ trước 0 ngày thì không so"
    assert out["days"][0]["date"] == "2026-11-05", "ngày ra chuỗi JSON"


def test_ads_rules_same_as_mcp():
    ctx = pages.context(fake, date(2026, 11, 11), "7")
    out = pages.ads(fake, ctx)
    assert out["lose_types"] == ["Can Cooler"] and out["untyped_spend"] == 96.91, out
    assert abs(out["campaigns"][0]["ctr_pct"] - 1.5) < 1e-9 and out["campaigns"][0]["cpm"] == 10.0
    assert out["funnel"][1]["note"] == "bước sau Meta đếm riêng, không so" and out["funnel"][1]["to_next_pct"] is None
    assert out["orders"] == 802


def test_alerts_forecast_range_like_tool():
    ctx = pages.context(fake, date(2026, 11, 11), "7")
    out = pages.alerts(fake, ctx)
    f = out["forecast"]
    assert f["total"] == 1851.0 and f["range"] == [1248, 2454], f
    assert out["alerts"][0]["event"] == "Veterans Day"
    assert f["actual"][1]["orders"] is None, "NaN thành null trong JSON"


def test_api_routes_with_fake_backend():
    from fastapi.testclient import TestClient

    from webapp.api import main

    main.fetch = fake
    main.version = lambda: "v1"
    main.last_complete_day = lambda: date(2026, 11, 11)
    c = TestClient(main.app)
    r = c.get("/api/page/overview?preset=7")
    assert r.status_code == 200 and r.json()["period"]["start"] == "2026-11-05", r.text
    n = len(seen)
    c.get("/api/page/overview?preset=7")
    assert len(seen) == n, "cùng phiên bản dữ liệu thì dùng cache, không hỏi lại BigQuery"
    main.version = lambda: "v2"
    c.get("/api/page/overview?preset=7")
    assert len(seen) > n, "phiên bản đổi (vừa nạp) thì đọc số mới"
    assert c.get("/api/page/xyz").status_code == 404 and c.get("/api/page/ads?preset=99").status_code == 400


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"  ✓ {name}")
    print("PASS")
