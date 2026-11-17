"""Số cho từng trang dashboard React. Mỗi hàm nhận `fetch(sql, params) -> DataFrame` (thật: BigQuery khoá chỉ đọc;
test: dữ liệu giả) và trả dict JSON được. SQL ở dashboard/queries.py, phép tính chung ở dashboard/kpi.py: cùng quy tắc
với bản Streamlit và server MCP (MER/ROAS từ tổng, type lỗ theo hoà vốn, bỏ '(không theo type)', ngày dở không tính).
"""

import math
from datetime import date, timedelta

import pandas as pd

from dashboard import kpi
from dashboard import queries as q

RFM_ORDER = ["Champions", "Loyal", "Mới quay lại", "Cần chú ý", "Khách mới", "Ngủ đông", "Có nguy cơ",
             "Không thể để mất", "Đã mất"]
ABC_ORDER = ["A", "B", "C", "D", "Mới"]
PRESET_KEYS = {"7": "7 ngày", "14": "14 ngày", "28": "28 ngày", "month": "Tháng này"}


def clean(v):
    """Về kiểu JSON: ngày → 'YYYY-MM-DD', NaN → None, số numpy → số Python."""
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean(x) for x in v]
    if isinstance(v, pd.Timestamp):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        v = v.item()
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def records(df: pd.DataFrame) -> list[dict]:
    return [clean(r) for r in df.to_dict("records")] if not df.empty else []


def data_complete_through(fetch) -> date:
    """Kho có số trọn tới ngày nào: gold.load_status (theo lúc nạp). Bảng chưa dựng thì đoán như cũ:
    ngày mới nhất có đơn − 1 (16/11: nạp 00:07 Phoenix thì cách đoán này mất trọn 1 ngày)."""
    from google.api_core.exceptions import NotFound

    try:
        st = fetch(q.LOAD_STATUS, None)
        if not st.empty and pd.notna(st["d"].iloc[0]):
            return pd.Timestamp(st["d"].iloc[0]).date()
    except NotFound:
        pass
    frame = fetch(q.LATEST_LOADED, None)
    if frame.empty or pd.isna(frame["d"].iloc[0]):
        raise ValueError("Chưa có bằng chứng ngày hoàn tất trong kho")
    latest = frame["d"].iloc[0]
    return pd.Timestamp(latest).date() - timedelta(days=1)


def context(fetch, clock_done: date, preset: str) -> dict:
    end_max = min(clock_done, data_complete_through(fetch))
    start, end = kpi.period(PRESET_KEYS.get(preset, "7 ngày"), end_max)
    p_start, p_end = kpi.previous(start, end)
    return {"end_max": end_max, "start": start, "end": end, "p_start": p_start, "p_end": p_end,
            "breakeven": kpi.breakeven_mer()}


def _rng(a, b):
    return {"since": a, "until": b}


def overview(fetch, ctx: dict) -> dict:
    rows = fetch(q.DAILY_KPI, _rng(ctx["p_start"], ctx["end"])).to_dict("records")
    for r in rows:
        r["date"] = pd.Timestamp(r["date"]).date()
    cur = [r for r in rows if ctx["start"] <= r["date"] <= ctx["end"]]
    prev = [r for r in rows if ctx["p_start"] <= r["date"] <= ctx["p_end"]]
    t, b = kpi.totals(cur), kpi.totals(prev)
    comparable = b["days"] == t["days"] == (ctx["end"] - ctx["start"]).days + 1          # kỳ trước thiếu ngày (đầu kho) thì không so
    change = {k: (kpi.change_pct(t[k], b[k]) if comparable else None)
              for k in ["rev", "orders", "aov", "spend", "mer", "cpo", "cm_est"]}
    expected_days = (ctx['end'] - ctx['start']).days + 1
    if len({r['date'] for r in cur}) != expected_days:
        for key in t:
            if key != 'days': t[key] = None
    days_by_date = {r['date']: r for r in cur}
    chart_days = [days_by_date.get(ctx['start'] + timedelta(days=i),
        dict(date=ctx['start'] + timedelta(days=i), rev=None, orders=None, spend=None, mer=None, cpo=None, cm_est=None)) for i in range(expected_days)]
    cogs, fee = kpi.rates()
    rf = fetch(q.REFUNDS, {"since": ctx["start"], "until": ctx["end"], "p_since": ctx["p_start"],
                           "p_until": ctx["p_end"]}).iloc[0].to_dict()
    num = lambda v: float(v) if v is not None and pd.notna(v) else None   # noqa: E731  (sum rỗng = null/NaN)
    amount, p_amount = num(rf["amount"]), num(rf["p_amount"])
    refunds = {"amount": amount, "orders": int(rf["orders"]) if pd.notna(rf["orders"]) else None, "p_amount": p_amount,
               "p_orders": int(rf["p_orders"]) if pd.notna(rf["p_orders"]) else None, "pct_of_rev": 100 * amount / t["rev"] if amount is not None and t["rev"] else None,
               "change": kpi.change_pct(amount, p_amount) if comparable else None}
    return clean({"totals": t, "previous": b, "change": change, "comparable": comparable,
                  "cogs_rate": cogs, "fee_rate": fee, "expected_days": expected_days, "days": chart_days, "refunds": refunds})


def ads(fetch, ctx: dict) -> dict:
    r = _rng(ctx["start"], ctx["end"])
    kd = fetch(q.DAILY_KPI, r)
    orders = int(kd["orders"].sum()) if not kd.empty else None   # đơn Shopify thật, so với mua Meta tự nhận
    flags = kpi.roas_flags(fetch(q.TYPE_ROAS, r).to_dict("records"), ctx["breakeven"])
    lose = [f for f in flags if f["status"] == "đang lỗ"]
    c = fetch(q.CAMPAIGNS, r)
    camps = []
    def ratio(numerator, denominator, scale=1):
        return scale * numerator / denominator if kpi.known(numerator) and kpi.known(denominator) and denominator else None
    for x in c.to_dict("records"):
        imp, spend = x["impressions"], x["spend"]
        camps.append({**x, "ctr_pct": ratio(x["link_clicks"], imp, 100),
                      "cpm": ratio(spend, imp, 1000),
                      "roas_meta": ratio(x["meta_purchase_value"], spend)})
    f = fetch(q.FUNNEL, r).iloc[0].to_dict()
    steps = [("Hiển thị", "impressions"), ("Click link", "link_clicks"), ("Xem sản phẩm", "view_content"),
             ("Thêm giỏ", "add_to_cart"), ("Thanh toán", "checkout"), ("Mua (Meta)", "purchases")]
    funnel = []
    for i, (name, key) in enumerate(steps):
        v = f.get(key)
        nxt = f.get(steps[i + 1][1]) if i + 1 < len(steps) else None
        if not v or nxt is None or pd.isna(nxt):
            conv, note = None, None
        elif nxt > v:   # Meta đếm riêng từng bước: không ra % chuyển
            conv, note = None, "bước sau Meta đếm riêng, không so"
        else:
            conv, note = 100 * nxt / v, None
        funnel.append({"step": name, "value": v, "to_next_pct": conv, "note": note})
    return clean({"types": flags, "lose_count": len(lose), "lose_spend": sum(x["spend"] for x in lose),
                  "lose_types": [x["product_line"] for x in lose],
                  "untyped_spend": sum(x["spend"] for x in flags if x["product_line"] == kpi.UNTYPED and x["spend"] is not None),
                  "campaigns": camps[:1000], "truncated": len(camps) > 1000, "funnel": funnel, "orders": orders})


def products(fetch, ctx: dict) -> dict:
    a = fetch(q.ABC, None)
    abc = {"groups": [], "top": [], "window": None}
    if not a.empty:
        s = a.groupby("abc_class").agg(mau=("product_title", "count"), rev=("revenue", "sum")).reindex(ABC_ORDER)
        s = s.fillna(0)
        tr, tn = s["rev"].sum(), s["mau"].sum()
        abc["groups"] = [{"cls": k, "mau": int(r.mau), "rev_pct": 100 * r.rev / tr if tr else None,
                          "mau_pct": 100 * r.mau / tn if tn else None} for k, r in s.iterrows()]
        top = a[~a["is_new"].astype(bool)].sort_values("revenue", ascending=False).head(15)
        abc["top"] = records(top[["product_title", "product_line", "abc_class", "revenue", "units", "share_pct"]])
        abc["window"] = [clean(a["window_start"].iloc[0]), clean(a["as_of_date"].iloc[0])]
    sp = fetch(q.SPECIES, {"since": ctx["start"], "until": ctx["end"], "p_since": ctx["p_start"],
                           "p_until": ctx["p_end"]})
    kd = fetch(q.DAILY_KPI, _rng(ctx['p_start'], ctx['end']))
    dates = set(pd.to_datetime(kd['date']).dt.date) if not kd.empty else set()
    comparable = all(ctx['p_start'] + timedelta(days=i) in dates for i in range((ctx['end']-ctx['p_start']).days+1))
    species, none_rev, total = [], 0, 0
    if not sp.empty:
        total = sp["rev"].sum()
        none_rev = sp.loc[sp["species"] == "(không có species)", "rev"].sum()
        t10 = sp[sp["species"] != "(không có species)"].sort_values("rev", ascending=False).head(10).copy()
        t10["change_pct"] = 100 * (t10["rev"] - t10["rev_truoc"]) / t10["rev_truoc"].where(t10["rev_truoc"] > 0)
        if not comparable: t10["change_pct"] = None
        species = records(t10)
    r = _rng(ctx["start"], ctx["end"])
    rl = fetch(q.RETURNS_BY_LINE, r)
    returns = {"lines": [], "top": [], "sold": 0, "returned": 0, "value": 0.0, "pct": None}
    if not rl.empty:
        rl["return_pct"] = 100 * rl["returned"] / rl["sold"]
        returns.update(lines=records(rl), sold=int(rl["sold"].sum()), returned=int(rl["returned"].sum()),
                       value=float(rl["returned_value"].sum()))
        returns["pct"] = 100 * returns["returned"] / returns["sold"] if returns["sold"] else None
        top = fetch(q.RETURNS_TOP, r)
        if not top.empty:
            top["return_pct"] = 100 * top["returned"] / top["sold"]
            returns["top"] = records(top)
    explore = fetch(q.PRODUCTS, r)
    return clean({"explore": records(explore.head(1000)), "truncated": len(explore) > 1000, "comparable": comparable, "abc": abc, "returns": returns,
                  "species": species, "species_none_rev": none_rev,
                  "species_none_pct": 100 * none_rev / total if total else None})


def customers(fetch, ctx: dict) -> dict:
    w_start, w_end = kpi.weeks_window(ctx["end_max"], 12)
    cw = fetch(q.CUSTOMERS_WEEKLY, _rng(w_start, w_end))
    cw = cw.sort_values("tuan") if not cw.empty else cw
    moi, cu = (cw["khach_moi"].sum(), cw["khach_cu"].sum()) if not cw.empty else (0, 0)
    rt = fetch(q.REPEAT_BY_TYPE, None)
    repeat = {"rows": records(rt), "as_of": clean(rt["as_of"].iloc[0]) if not rt.empty else None,
              "total": {"khach": rt["khach"].sum(), "mua_lan_2": rt["mua_lan_2"].sum()} if not rt.empty else None}
    r = fetch(q.RFM, None)
    rfm = []
    if not r.empty:
        r = r.set_index("segment").reindex(RFM_ORDER).dropna(how="all").reset_index()
        tk, trv = r["khach"].sum(), r["doanh_thu"].sum()
        rfm = [{"segment": x.segment, "khach": x.khach, "khach_pct": 100 * x.khach / tk if tk else None,
                "rev_pct": 100 * x.doanh_thu / trv if trv else None} for x in r.itertuples()]
    co = fetch(q.COHORT, None)
    ew = fetch(q.EMAIL_WEEKLY, _rng(w_start, w_end))
    if not ew.empty:
        ew = ew.sort_values("tuan")
        ew["email"] = ew["campaign"] + ew["flow"]
        ew["email_pct"] = 100 * ew["email"] / ew["rev"].where(ew["rev"] > 0)
    return clean({"weeks": [w_start, w_end], "orders_weekly": records(cw),
                  "returning_pct": 100 * cu / (moi + cu) if moi + cu else None, "repeat": repeat, "rfm": rfm,
                  "clv": records(fetch(q.CLV, None)), "rfm_as_of": clean(r["as_of"].iloc[0]) if not r.empty else None,
                  "cohort": records(co), "email_weekly": records(ew)})


def alerts(fetch, ctx: dict) -> dict:
    end = ctx["end_max"]
    since = end - timedelta(days=13)
    al = fetch(q.ALERTS, _rng(since, end))
    fc = fetch(q.FORECAST, None)
    out = {"since": since, "until": end, "alerts": records(al), "forecast": None}
    if not fc.empty:
        origin = pd.Timestamp(fc["origin"].iloc[0]).date()
        dates = [pd.Timestamp(d).date() for d in fc["date"]]
        valid = len(dates) == 14 and dates == [origin + timedelta(days=i) for i in range(1, 15)]
        valid = valid and all(kpi.known(x) for col in ("fc", "lo", "hi", "backtest_total_p80_pct") for x in fc[col])
        valid = valid and all(0 <= x.lo <= x.fc <= x.hi for x in fc.itertuples())
        valid = valid and all(pd.Timestamp(x).date() == origin for x in fc["origin"])
        valid = valid and all(float(x) >= 0 for x in fc["backtest_total_p80_pct"])
        if not valid:
            out["forecast_error"] = "Dự báo không đủ 14 ngày hoặc cận không hợp lệ; không hiển thị."
            return clean(out)
        # như MCP forecast_orders (total_range): làm tròn tổng trước rồi ± p80, 2 nơi ra cùng số
        total = round(float(fc["fc"].sum()), 0)
        p80 = float(fc["backtest_total_p80_pct"].iloc[0])
        actual = fetch(q.ORDERS_DAILY, _rng(end - timedelta(days=27), end))
        out["forecast"] = {"origin": origin, "stale": origin != end, "days": records(fc[["date", "fc", "lo", "hi"]]), "total": total, "p80_pct": p80,
                           "range": [max(0, round(total * (1 - p80 / 100))), round(total * (1 + p80 / 100))],
                           "actual": records(actual),
                           "actual_mean": float(actual["orders"].mean()) if not actual.empty else None}
    return clean(out)


PAGES = {"overview": overview, "ads": ads, "products": products, "customers": customers, "alerts": alerts}
