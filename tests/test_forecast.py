"""Kiểm forecast/backtest.py trên dữ liệu GIẢ (không BigQuery, không khoá).

Chạy từ thư mục gốc:  python tests/test_forecast.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from forecast import backtest as b  # noqa: E402

DAYS = pd.date_range("2026-03-01", periods=200, freq="D")
FACTOR = np.array([1.2, 1.1, 1.0, 0.9, 0.8, 0.85, 1.15])   # theo dayofweek (thứ Hai = 0)


def make(level, spend=None, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    f = FACTOR[DAYS.dayofweek]
    orders = np.asarray(level, dtype=float) * f * np.exp(rng.normal(0, noise, len(DAYS)))
    if spend is None:   # spend dao động như thật (đứng yên thì spend_reg không học được)
        spend = 1000.0 * np.exp(np.random.default_rng(9).normal(0, 0.2, len(DAYS)))
    return pd.DataFrame({"orders": orders, "spend": spend}, index=DAYS)


# 1. Mức không đổi, không nhiễu: mốc ngây thơ và level_weekday đoán đúng tuyệt đối; ETS gần đúng
df = make(np.full(len(DAYS), 100.0))
res = b.score(b.backtest(df)).set_index(["model", "tam_xa"])
assert res.loc[("naive_season", "1–14"), "wape_pct"] == 0.0
assert res.loc[("level_weekday", "1–14"), "wape_pct"] < 0.5, res.loc[("level_weekday", "1–14")]
assert res.loc[("ets", "1–14"), "wape_pct"] < 2.0, res.loc[("ets", "1–14")]

# 2. level_weekday lấy ĐÚNG ngày cùng thứ cho cả 14 ngày (lỗi lệch 1 ngày sẽ ra hệ số của thứ khác)
hist, future = df.iloc[:150], df.iloc[150:164]
fc = b.f_level_weekday(hist, future)["mean"].to_numpy()
level = hist["orders"].iloc[-7:].mean()
assert np.allclose(fc, level * FACTOR[future.index.dayofweek] / FACTOR.mean(), rtol=1e-6), (fc, future.index.dayofweek)

# 3. KHÔNG NHÌN TRƯỚC: đổi orders tương lai thành rác thì dự báo tại mốc không đổi (mọi mô hình)
o = b.origins(df)[-1]
hist, future = df.loc[:o], df.loc[o:].iloc[1:b.HORIZON + 1]
junk = future.assign(orders=9999.0)
for name, fn in b.FORECASTERS.items():
    a1, a2 = fn(hist, future)["mean"].to_numpy(), fn(hist, junk)["mean"].to_numpy()
    assert np.allclose(a1, a2, equal_nan=True), f"{name} nhìn thấy orders tương lai"

# 4. Mốc cách 7 ngày, mốc cuối còn đúng 14 ngày thật phía sau, mốc đầu đủ TRAIN_DAYS
os_ = b.origins(df)
assert all((y - x).days == b.STEP for x, y in zip(os_, os_[1:]))
assert (df.index[-1] - os_[-1]).days == b.HORIZON and len(os_) <= b.N_ORIGINS
assert df.index.get_loc(os_[0]) >= b.TRAIN_DAYS - 1

# 5. Spend đổi bậc (như 10/10 gấp đôi): đơn = 0,05 × spend × hệ số thứ. Mô hình theo spend gần đúng tuyệt đối,
#    mô hình không điều kiện thua rõ ở mốc ngay trước bước nhảy.
# (spend phải dao động quanh mỗi bậc như thật: spend đứng yên thì hồi quy không tách được hệ số spend)
spend = np.where(np.arange(len(DAYS)) < 160, 1000.0, 2000.0) * np.exp(np.random.default_rng(3).normal(0, 0.2, len(DAYS)))
df5 = make(0.05 * spend, spend=spend)
res5 = b.score(b.backtest(df5)).set_index(["model", "tam_xa"])
assert res5.loc[("spend_reg", "1–14"), "wape_pct"] < 0.5, res5.loc[("spend_reg", "1–14")]
assert res5.loc[("naive_season", "1–14"), "wape_pct"] > 5, res5.loc[("naive_season", "1–14")]

# 6. Có nhiễu: khoảng 80% của ets, spend_reg phủ khoảng 60–97% (không quá hẹp, không vô nghĩa); bias nhỏ
df6 = make(np.full(len(DAYS), 100.0), spend=1000.0 * np.exp(np.random.default_rng(1).normal(0, 0.2, len(DAYS))),
           noise=0.15, seed=2)
res6 = b.score(b.backtest(df6)).set_index(["model", "tam_xa"])
for m in ["ets", "spend_reg"]:
    cov = res6.loc[(m, "1–14"), "phu_80_pct"]
    assert 60 <= cov <= 97, (m, cov)
    assert abs(res6.loc[(m, "1–14"), "bias_pct"]) < 6, (m, res6.loc[(m, "1–14")])
assert pd.isna(res6.loc[("naive_season", "1–14"), "phu_80_pct"]), "mốc ngây thơ không có khoảng"

# 7. Mô hình hỏng ở 1 mốc không làm dừng cả backtest; score chỉ so trên ô mọi mô hình đều có
df7 = df6.copy()
df7.loc[df7.index[150:], "spend"] = np.nan      # spend_reg không dự báo được về sau
sc = b.score(b.backtest(df7))
assert sc.groupby("tam_xa")["n"].nunique().eq(1).all(), "mọi mô hình so trên cùng số ô"

# 8. Chỉnh khoảng: khoảng gốc cố ý HẸP một nửa (phủ ~50%) → sau chỉnh phủ ~80%, k ≈ 2; k ở mốc o không đổi khi
#    đổi số thật của những ngày sau o (kể cả ngày thuộc mốc trước có cửa sổ chồng lên o)
rng = np.random.default_rng(5)
rows = []
for i, o in enumerate(pd.date_range("2026-06-01", periods=30, freq="7D")):
    for h in range(1, 15):
        z = 1.2816 * 0.15
        rows.append({"origin": o, "model": "ets", "h": h, "date": o + pd.Timedelta(days=h),
                     "actual": 100 * np.exp(rng.normal(0, 0.3)), "fc": 100.0,
                     "lo": 100 * np.exp(-z), "hi": 100 * np.exp(z)})
fake = pd.DataFrame(rows)
tab = b.calibration_table(fake).set_index("model").loc["ets"]
assert 40 <= tab["phu_goc_pct"] <= 60 and 72 <= tab["phu_chinh_pct"] <= 88, tab
assert 1.6 <= tab["k_cuoi"] <= 2.4, tab
cal1 = b.calibrate(fake)
o = fake["origin"].unique()[10]
fake2 = fake.copy()
fake2.loc[fake2["date"] > o, "actual"] = 1e6
cal2 = b.calibrate(fake2)
k1 = cal1.loc[cal1["origin"] == o, "k"].iloc[0]
k2 = cal2.loc[cal2["origin"] == o, "k"].iloc[0]
assert k1 == k2 and not np.isnan(k1), (k1, k2)
assert cal1.loc[cal1["origin"] == fake["origin"].unique()[3], "k"].isna().all(), "chưa đủ 4 mốc trước thì để trống"

print("PASS: forecast backtest (chỉnh khoảng cuốn chiếu không nhìn trước, đoán đúng khi không nhiễu, đúng ngày cùng thứ, không nhìn trước, mốc cách 7 ngày, "
      "spend đổi bậc, khoảng 80% hợp lý, so trên cùng ô)")
