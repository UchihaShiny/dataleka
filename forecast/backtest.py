"""Mô hình 8, phần B (dự báo), bước 1: BACKTEST CUỐN CHIẾU dự báo orders 14 ngày tới.

Bài học mục 3f: không trộn ngẫu nhiên; chỉ dùng QUÁ KHỨ đoán TƯƠNG LAI. Mỗi mốc (origin) cách nhau 7 ngày: học trên dữ
liệu tới hết ngày mốc, dự báo 14 ngày sau, so với số thật. Gộp sai số mọi mốc.

4 mô hình (Huy Anh chọn 12/11: cả không điều kiện lẫn có điều kiện):
  KHÔNG ĐIỀU KIỆN (không biết trước spend):
    naive_season : bằng cùng thứ của 7 ngày cuối (mốc ngây thơ theo mùa, bài học 3a)
    level_weekday: mức 7 ngày cuối × hệ số thứ (trung vị giá trị ÷ mức 7 ngày trước nó, 8 ngày cùng thứ). Y hệt
                   expected của mart_anomaly_daily, giữ nguyên mức cho cả 14 ngày.
    ets          : ETS lỗi nhân, xu hướng cộng có hãm (damped), mùa tuần nhân; học trên TRAIN_DAYS ngày cuối. Có
                   khoảng 80%.
  CÓ ĐIỀU KIỆN (biết spend của 14 ngày tới, dạng "nếu chi X thì được khoảng Y đơn"):
    spend_reg    : hồi quy log(orders) ~ log(spend) + thứ trong tuần, học trên REG_DAYS ngày cuối; dự báo bằng spend
                   THẬT của 14 ngày đó. Có khoảng 80%. Thắng ở đây chỉ chứng minh "biết spend thì đoán được", không
                   chứng minh đoán được spend.
Sai số (bài học 3f): WAPE = tổng |lệch| ÷ tổng thật (không dùng MAPE vì ngày ít đơn); bias = tổng (dự báo − thật) ÷
tổng thật (dương = đoán cao); độ phủ khoảng 80% (phải gần 80%; thấp hơn nhiều = tự tin quá mức).

Không ghi gì vào BigQuery. Đọc gold.daily_performance (khoá GCP chỉ đọc). Chạy từ thư mục gốc:
    python -m forecast.backtest
    python -m forecast.backtest --csv duong_dan.csv   (đọc CSV có cột date, orders, spend; không cần khoá)
"""

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
START = "2026-03-01"   # như anomaly_start: bỏ điểm gãy 2/2026
HORIZON = 14
STEP = 7
TRAIN_DAYS = 84        # ETS: 12 tuần cuối
REG_DAYS = 56          # hồi quy spend: 8 tuần cuối (quan hệ spend → đơn đổi theo thời gian)
N_ORIGINS = 16         # số mốc tối đa (mới nhất trở về trước)
ALPHA = 0.2            # khoảng 80%
SEED = 20261112        # hạt giống mô phỏng khoảng ETS (chạy lại ra đúng số)
MODELS = ["naive_season", "level_weekday", "ets", "spend_reg"]
# Bảng 35 ngày chỉ để THEO DÕI (12/11: tổng 30 ngày lệch TB 24%, tệ nhất 63% nên chỉ dùng thật 14 ngày; xem lại khi
# có Q4). spend_hold (spend_reg với spend giữ bằng TB 7 ngày) đã thử 12/11 và bị bỏ: 14 ngày WAPE 30,5, tệ hơn naive.
LONG_MODELS = ["ets"]

SQL = """
select date, orders, spend
from `{p}.gold.daily_performance`
where date >= '{start}'
  and date <= (select complete_through from `{p}.gold.load_status`)  -- chỉ ngày đã trọn (theo lúc nạp, 16/11)
order by date
"""


# ---------- 4 mô hình: nhận lịch sử tới hết ngày mốc, trả DataFrame (mean, lo, hi) cho HORIZON ngày sau ----------

def f_naive_season(hist: pd.DataFrame, future: pd.DataFrame) -> pd.DataFrame:
    last_week = hist["orders"].iloc[-7:].to_numpy(dtype=float)
    mean = np.array([last_week[h % 7] for h in range(len(future))])
    return pd.DataFrame({"mean": mean, "lo": np.nan, "hi": np.nan}, index=future.index)


def f_level_weekday(hist: pd.DataFrame, future: pd.DataFrame, weeks: int = 8) -> pd.DataFrame:
    y = hist["orders"].astype(float)
    level_prev = y.shift(1).rolling(7).mean()          # mức 7 ngày NGAY TRƯỚC mỗi ngày
    ratio = (y / level_prev.where(level_prev > 0))
    level = y.iloc[-7:].mean()
    mean = []
    n = len(y)
    for h in range(len(future)):
        # ngày dự báo thứ j = h + 1 nằm ở vị trí n − 1 + j; ngày cùng thứ gần nhất trong lịch sử lùi về bội số của 7
        j = h + 1
        nearest = n - 1 + j - 7 * (-(-j // 7))
        idx = [nearest - 7 * k for k in range(weeks)]
        r = ratio.iloc[[i for i in idx if i >= 0]].dropna()
        mean.append(level * (r.median() if len(r) else 1.0))
    return pd.DataFrame({"mean": mean, "lo": np.nan, "hi": np.nan}, index=future.index)


def f_ets(hist: pd.DataFrame, future: pd.DataFrame) -> pd.DataFrame:
    from statsmodels.tsa.exponential_smoothing.ets import ETSModel

    y = hist["orders"].astype(float).iloc[-TRAIN_DAYS:].clip(lower=0.5)   # lỗi nhân cần > 0
    y.index = pd.DatetimeIndex(y.index, freq="D")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = ETSModel(y, error="mul", trend="add", damped_trend=True, seasonal="mul",
                       seasonal_periods=7).fit(disp=False, maxiter=2000)
        # lỗi nhân: khoảng dự báo tính bằng MÔ PHỎNG ngẫu nhiên. Cố định hạt giống để chạy lại ra đúng số cũ
        # (12/11: 2 lần chạy cho độ phủ ETS 72,3 rồi 70,5 vì không cố định).
        frame = fit.get_prediction(start=len(y), end=len(y) + len(future) - 1, simulate_repetitions=2000,
                                   rng=np.random.default_rng(SEED)).summary_frame(alpha=ALPHA)
    return pd.DataFrame({"mean": frame["mean"].to_numpy(), "lo": frame["pi_lower"].to_numpy(),
                         "hi": frame["pi_upper"].to_numpy()}, index=future.index)


def _design(frame: pd.DataFrame) -> np.ndarray:
    dow = pd.DatetimeIndex(frame.index).dayofweek
    dummies = np.column_stack([(dow == d).astype(float) for d in range(1, 7)])   # thứ Hai là gốc
    return np.column_stack([np.ones(len(frame)), np.log(frame["spend"].to_numpy(dtype=float)), dummies])


def f_spend_reg(hist: pd.DataFrame, future: pd.DataFrame) -> pd.DataFrame:
    import statsmodels.api as sm

    train = hist.iloc[-REG_DAYS:]
    train = train[(train["spend"] > 0) & (train["orders"] > 0)]
    if np.ptp(np.log(train["spend"].to_numpy(dtype=float))) < 1e-6:
        raise ValueError("spend không đổi trong cửa sổ học, không tách được hệ số spend")
    fit = sm.OLS(np.log(train["orders"].to_numpy(dtype=float)), _design(train)).fit()
    if (future["spend"].isna() | (future["spend"] <= 0)).any():
        return pd.DataFrame({"mean": np.nan, "lo": np.nan, "hi": np.nan}, index=future.index)
    pred = fit.get_prediction(_design(future)).summary_frame(alpha=ALPHA)
    # trả trung vị exp(mu); khoảng dự báo của 1 ngày (obs_ci) trên thang log rồi đổi lại
    return pd.DataFrame({"mean": np.exp(pred["mean"].to_numpy()), "lo": np.exp(pred["obs_ci_lower"].to_numpy()),
                         "hi": np.exp(pred["obs_ci_upper"].to_numpy())}, index=future.index)


FORECASTERS = {"naive_season": f_naive_season, "level_weekday": f_level_weekday, "ets": f_ets,
               "spend_reg": f_spend_reg}


# ---------- backtest ----------

def origins(df: pd.DataFrame, horizon: int = HORIZON) -> list:
    """Mốc cách nhau STEP ngày, mốc mới nhất là ngày cuối còn đủ horizon ngày thật phía sau; cần đủ TRAIN_DAYS."""
    dates = list(df.index)
    out = []
    i = len(dates) - 1 - horizon
    while i >= TRAIN_DAYS - 1 and len(out) < N_ORIGINS:
        out.append(dates[i])
        i -= STEP
    return sorted(out)


def backtest(df: pd.DataFrame, horizon: int = HORIZON, models: list | None = None) -> pd.DataFrame:
    """1 dòng = 1 mốc × 1 mô hình × 1 ngày dự báo (h = 1..horizon)."""
    df = df.sort_index()
    rows = []
    for o in origins(df, horizon):
        hist = df.loc[:o]
        future = df.loc[o:].iloc[1:horizon + 1]
        for name, fn in FORECASTERS.items():
            if models and name not in models:
                continue
            try:
                fc = fn(hist, future)
            except Exception as error:   # 1 mô hình hỏng ở 1 mốc thì ghi lại, không dừng cả backtest
                print(f"  ! {name} ở mốc {o.date()}: {type(error).__name__} {str(error)[:80]}")
                fc = pd.DataFrame({"mean": np.nan, "lo": np.nan, "hi": np.nan}, index=future.index)
            for h, (d, r) in enumerate(fc.iterrows(), start=1):
                rows.append({"origin": o, "model": name, "h": h, "date": d, "actual": float(future.loc[d, "orders"]),
                             "fc": r["mean"], "lo": r["lo"], "hi": r["hi"]})
    return pd.DataFrame(rows)


MIN_CAL_ORIGINS = 4   # chỉnh khoảng cần ít nhất 4 mốc trước đó


def k_needed(bt: pd.DataFrame) -> pd.Series:
    """Hệ số nới k nhỏ nhất để số thật lọt vào khoảng, tính trên thang log quanh dự báo:
    khoảng mới = fc × (lo/fc)^k … fc × (hi/fc)^k. k = 1 là khoảng gốc; k > 1 là nới rộng."""
    m = bt["fc"].clip(lower=0.5)
    r = np.log(bt["actual"].clip(lower=0.5) / m)
    up = np.log(bt["hi"].clip(lower=0.5) / m)
    down = np.log(bt["lo"].clip(lower=0.5) / m)
    with np.errstate(divide="ignore", invalid="ignore"):
        k = np.where(r >= 0, r / up, r / down)
    k = pd.Series(k, index=bt.index).where(bt["lo"].notna())
    return k.replace([np.inf, -np.inf], 1e9).clip(lower=0)


def calibrate(bt: pd.DataFrame) -> pd.DataFrame:
    """Chỉnh khoảng CUỐN CHIẾU: ở mỗi mốc o, k = phân vị 80% của k_needed trên các ngày ĐÃ BIẾT tại o (date ≤ o) của
    các mốc trước. Không dùng ngày sau o (kể cả của mốc trước có cửa sổ chồng lên o), nên không nhìn trước.
    Mốc chưa đủ MIN_CAL_ORIGINS mốc trước thì để trống."""
    bt = bt.copy()
    bt["k_need"] = k_needed(bt)
    bt["k"] = np.nan
    for model, g in bt[bt["lo"].notna()].groupby("model"):
        for o in sorted(g["origin"].unique()):
            past = g[(g["origin"] < o) & (g["date"] <= o)]
            if past["origin"].nunique() >= MIN_CAL_ORIGINS:
                bt.loc[(bt["model"] == model) & (bt["origin"] == o), "k"] = past["k_need"].quantile(1 - ALPHA)
    m = bt["fc"].clip(lower=0.5)
    bt["lo_k"] = m * (bt["lo"].clip(lower=0.5) / m) ** bt["k"]
    bt["hi_k"] = m * (bt["hi"].clip(lower=0.5) / m) ** bt["k"]
    return bt


def calibration_table(bt: pd.DataFrame) -> pd.DataFrame:
    """Độ phủ trước và sau chỉnh, trên CÙNG các ô đã chỉnh được; k_cuoi = k dùng thật (ước trên mọi ngày backtest)."""
    cal = calibrate(bt)
    out = []
    for model, g in cal[cal["lo"].notna()].groupby("model"):
        c = g[g["k"].notna()]
        inside = lambda lo, hi: round(100 * ((c["actual"] >= lo) & (c["actual"] <= hi)).mean(), 1)  # noqa: E731
        out.append({"model": model, "n": len(c), "so_moc": c["origin"].nunique(),
                    "phu_goc_pct": inside(c["lo"], c["hi"]), "phu_chinh_pct": inside(c["lo_k"], c["hi_k"]),
                    "k_cuoi": round(g["k_need"].quantile(1 - ALPHA), 2)})
    return pd.DataFrame(out)


def total_table(bt: pd.DataFrame) -> pd.DataFrame:
    """Sai số của TỔNG 14 ngày mỗi mốc (khác WAPE ngày: các ngày lệch bù trừ nhau, nhưng đoán thấp đều thì cộng dồn).
    p80_abs_pct = 80% số mốc có |lệch tổng| không quá mức này: dùng làm khoảng ±% cho tổng 14 ngày."""
    out = []
    for model, g in bt.dropna(subset=["fc"]).groupby("model"):
        tot = g.groupby("origin")[["fc", "actual"]].sum()
        lech = 100 * (tot["fc"] - tot["actual"]) / tot["actual"]
        out.append({"model": model, "so_moc": len(tot), "tb_abs_pct": round(lech.abs().mean(), 1),
                    "bias_pct": round(lech.mean(), 1), "p80_abs_pct": round(lech.abs().quantile(0.8), 1),
                    "te_nhat_pct": round(lech.abs().max(), 1)})
    order = {m: i for i, m in enumerate(MODELS)}
    return pd.DataFrame(out).sort_values("model", key=lambda c: c.map(order))


def score(bt: pd.DataFrame) -> pd.DataFrame:
    """WAPE, bias, MAE, độ phủ 80% theo mô hình và nhóm tầm xa (1–7, 8–14 ngày). Chỉ so trên ô MỌI mô hình đều có
    dự báo, để không mô hình nào được lợi vì bỏ qua mốc khó."""
    ok = bt.pivot_table(index=["origin", "h"], columns="model", values="fc").dropna().index
    bt = bt.set_index(["origin", "h"]).loc[ok].reset_index()
    bt["tam_xa"] = np.where(bt["h"] <= 7, "1–7", "8–14")
    out = []
    for (model, tam), g in list(bt.groupby(["model", "tam_xa"])) + [((m, "1–14"), g) for m, g in bt.groupby("model")]:
        err = g["fc"] - g["actual"]
        has_pi = g["lo"].notna()
        out.append({
            "model": model, "tam_xa": tam, "n": len(g),
            "wape_pct": round(100 * err.abs().sum() / g["actual"].sum(), 1),
            "bias_pct": round(100 * err.sum() / g["actual"].sum(), 1),
            "mae": round(err.abs().mean(), 1),
            "phu_80_pct": (round(100 * ((g["actual"] >= g["lo"]) & (g["actual"] <= g["hi"]))[has_pi].mean(), 1)
                           if has_pi.any() else None),
        })
    res = pd.DataFrame(out)
    naive = res[res["model"] == "naive_season"].set_index("tam_xa")["wape_pct"]
    res["thang_naive_pct"] = res.apply(lambda r: round(100 * (1 - r["wape_pct"] / naive[r["tam_xa"]]), 1)
                                       if naive[r["tam_xa"]] > 0 else None, axis=1)
    order = {m: i for i, m in enumerate(MODELS)}
    return res.sort_values(["tam_xa", "model"], key=lambda c: c.map(order) if c.name == "model" else c)


LONG_HORIZON = 35   # chỉ theo dõi; dùng thật 14 ngày (Huy Anh chốt 12/11)
MONTH_DAYS = 30


def long_table(df: pd.DataFrame, ks: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """ETS dự báo LONG_HORIZON ngày: sai số theo tầm xa 1–14 / 15–28 / 29–35, độ phủ gốc và với k
    (k_cuoi của bảng 14 ngày, ước trên toàn bộ backtest nên KHÔNG phải ngoài mẫu); và sai số TỔNG 30 ngày từng mốc
    (thứ pacing tháng cần). Chỉ so trên mốc cả hai mô hình đều có."""
    bt = backtest(df, LONG_HORIZON, LONG_MODELS)
    ok = bt.pivot_table(index=["origin", "h"], columns="model", values="fc").dropna().index
    bt = bt.set_index(["origin", "h"]).loc[ok].reset_index()
    m = bt["fc"].clip(lower=0.5)
    k = bt["model"].map(ks)
    bt["lo_k"] = m * (bt["lo"].clip(lower=0.5) / m) ** k
    bt["hi_k"] = m * (bt["hi"].clip(lower=0.5) / m) ** k
    bt["tam_xa"] = pd.cut(bt["h"], [0, 14, 28, LONG_HORIZON], labels=["1–14", "15–28", "29–35"])
    rows = []
    for (model, tam), g in bt.groupby(["model", "tam_xa"], observed=True):
        err = g["fc"] - g["actual"]
        inside = lambda lo, hi: round(100 * ((g["actual"] >= lo) & (g["actual"] <= hi)).mean(), 1)  # noqa: E731
        rows.append({"model": model, "tam_xa": tam, "n": len(g),
                     "wape_pct": round(100 * err.abs().sum() / g["actual"].sum(), 1),
                     "bias_pct": round(100 * err.sum() / g["actual"].sum(), 1),
                     "phu_goc_pct": inside(g["lo"], g["hi"]), "phu_k_pct": inside(g["lo_k"], g["hi_k"])})
    tot = bt[bt["h"] <= MONTH_DAYS].groupby(["origin", "model"])[["fc", "actual"]].sum()
    month = tot["fc"].unstack("model")[LONG_MODELS].round(0)
    month["thật"] = tot["actual"].groupby("origin").first()
    for name in LONG_MODELS:
        month[f"lech_{name}_pct"] = (100 * (month[name] - month["thật"]) / month["thật"]).round(1)
    month.index = [pd.Timestamp(i).date() for i in month.index]
    return pd.DataFrame(rows), month


def load_bigquery() -> pd.DataFrame:
    from pipelines.bq import client, settings

    project = settings()[0]
    rows = client().query(SQL.format(p=project, start=START)).result()
    return frame_of(pd.DataFrame([dict(r) for r in rows]))


def frame_of(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["orders"] = df["orders"].astype(float)
    df["spend"] = pd.to_numeric(df["spend"], errors="coerce").astype(float)
    return df.set_index("date").sort_index()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", help="đọc CSV (date, orders, spend) thay vì BigQuery")
    args = parser.parse_args()
    df = frame_of(pd.read_csv(args.csv)) if args.csv else load_bigquery()
    print(f"Dữ liệu {df.index.min().date()} → {df.index.max().date()} ({len(df)} ngày)")
    bt = backtest(df)
    os_ = sorted(bt["origin"].unique())
    print(f"{len(os_)} mốc: {pd.Timestamp(os_[0]).date()} → {pd.Timestamp(os_[-1]).date()}, mỗi mốc dự báo {HORIZON} ngày\n")
    pd.set_option("display.width", 160)
    print(score(bt).to_string(index=False))
    print("\nWAPE thấp = tốt. bias dương = đoán cao. phu_80 nên gần 80. thang_naive > 0 = tốt hơn mốc ngây thơ.")
    print("spend_reg dùng spend THẬT của 14 ngày tới: chỉ trả lời 'nếu biết trước spend'.")
    print(f"\nTổng {HORIZON} ngày mỗi mốc (lệch tổng, không phải WAPE ngày):")
    print(total_table(bt).to_string(index=False))
    print(f"\nChỉnh khoảng 80% (cuốn chiếu, từ mốc thứ {MIN_CAL_ORIGINS + 1}; k > 1 = nới rộng):")
    print(calibration_table(bt).to_string(index=False))
    per_origin = (bt[bt["h"] <= HORIZON].assign(abs_err=lambda d: (d["fc"] - d["actual"]).abs())
                  .groupby(["origin", "model"]).apply(lambda g: round(100 * g["abs_err"].sum() / g["actual"].sum(), 1),
                                                      include_groups=False)
                  .unstack("model")[MODELS])
    per_origin.index = [pd.Timestamp(i).date() for i in per_origin.index]
    print("\nWAPE % từng mốc (14 ngày sau mốc):")
    print(per_origin.to_string())
    ks = calibration_table(bt).set_index("model")["k_cuoi"].to_dict()
    long, month = long_table(df, ks)
    print(f"\nDự báo {LONG_HORIZON} ngày (cho pacing tháng), k lấy từ bảng 14 ngày: "
          + ", ".join(f"{m} {ks[m]}" for m in LONG_MODELS))
    print(long.to_string(index=False))
    print(f"\nTổng {MONTH_DAYS} ngày sau mỗi mốc: dự báo so với thật (lech dương = đoán cao):")
    print(month.to_string())
    for name in LONG_MODELS:
        col = month[f"lech_{name}_pct"]
        print(f"  {name}: trung bình |lệch| {col.abs().mean():.1f}%, bias {col.mean():.1f}%, "
              f"tệ nhất {col.abs().max():.1f}%")


if __name__ == "__main__":
    main()
