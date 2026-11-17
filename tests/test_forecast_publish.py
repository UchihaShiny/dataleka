"""Kiểm forecast/publish.py bằng dữ liệu giả và BigQuery giả (không khoá, không ghi thật).

Chạy từ thư mục gốc:  python tests/test_forecast_publish.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from forecast import backtest as b  # noqa: E402
from forecast import publish as p  # noqa: E402

DAYS = pd.date_range("2026-03-01", periods=200, freq="D")
rng = np.random.default_rng(4)
spend = 1500 * np.exp(rng.normal(0, 0.25, len(DAYS)))
F = np.array([1.2, 1.1, 1.0, 0.9, 0.8, 0.85, 1.15])
df = pd.DataFrame({"orders": rng.poisson(0.04 * spend * F[DAYS.dayofweek]).astype(float), "spend": spend}, index=DAYS)

daily, spend_rows, summary = p.build(df, datetime(2026, 11, 12, tzinfo=timezone.utc))

# 1. 14 dòng ETS, ngày liền nhau ngay sau mốc, khoảng bao dự báo, đúng tên cột của schema
assert len(daily) == 14 and summary["origin"] == str(DAYS[-1].date())
dates = pd.to_datetime([r["date"] for r in daily])
assert (dates == pd.date_range(DAYS[-1] + pd.Timedelta(days=1), periods=14)).all()
assert [r["h"] for r in daily] == list(range(1, 15))
assert all(r["lo"] <= r["fc"] <= r["hi"] for r in daily)
assert all(list(r) == [n for n, _ in p.DAILY_SCHEMA] for r in daily)
assert all(r["k"] == daily[0]["k"] and r["backtest_wape_pct"] > 0 for r in daily)
assert all(r["backtest_total_p80_pct"] > 0 for r in daily) and spend_rows[0]["backtest_total_p80_pct"] > 0

# 1b. total_table: lệch tổng đúng định nghĩa trên 1 bộ giả tay
fake = pd.DataFrame({"origin": [1, 1, 2, 2], "model": "ets", "fc": [10, 10, 30, 30], "actual": [10, 10, 20, 20]})
tt = b.total_table(fake).set_index("model").loc["ets"]
assert tt["tb_abs_pct"] == 25.0 and tt["bias_pct"] == 25.0 and tt["te_nhat_pct"] == 50.0, tt

# 2. Hệ số lưu lại tính ra ĐÚNG số như mô hình spend_reg của backtest (tool MCP sẽ tính kịch bản từ hệ số này)
s = spend_rows[0]
assert list(s) == [n for n, _ in p.SPEND_SCHEMA]
future = pd.DataFrame({"spend": 2000.0}, index=pd.date_range(DAYS[-1] + pd.Timedelta(days=1), periods=7))
expect = b.f_spend_reg(df, future)["mean"].to_numpy()
dow = future.index.dayofweek
coef = [0, s["dow_tue"], s["dow_wed"], s["dow_thu"], s["dow_fri"], s["dow_sat"], s["dow_sun"]]
mine = np.exp(s["intercept"] + s["b_log_spend"] * np.log(2000.0) + np.array([coef[d] for d in dow]))
assert np.allclose(mine, expect, rtol=1e-9), (mine, expect)
assert 0.5 < s["b_log_spend"] < 1.5, s["b_log_spend"]           # dữ liệu giả: đơn tỉ lệ với spend → hệ số ~1
assert s["spend_min"] < s["spend_7d_mean"] < s["spend_max"] and s["t80"] > 1.28


# 3. Ghi: WRITE_TRUNCATE, JSONL đúng số dòng, lệch số dòng thì dừng
class FakeBQ:
    project = "demo"

    def __init__(self, rows_in_bq=None):
        self.sent, self.rows_in_bq = {}, rows_in_bq

    def load_table_from_file(self, handle, table_id, job_config):
        self.sent[table_id] = ([json.loads(x) for x in handle.read().decode("utf-8").splitlines()], job_config)
        return type("Job", (), {"result": lambda self: None})()

    def get_table(self, table_id):
        n = self.rows_in_bq if self.rows_in_bq is not None else len(self.sent[table_id][0])
        return type("T", (), {"num_rows": n})()


bq = FakeBQ()
assert p.write(bq, "forecast_daily", daily, p.DAILY_SCHEMA) == 14
rows, cfg = bq.sent["demo.gold.forecast_daily"]
assert rows == daily and cfg.write_disposition == "WRITE_TRUNCATE"
assert [f.name for f in cfg.schema] == [n for n, _ in p.DAILY_SCHEMA]
try:
    p.write(FakeBQ(rows_in_bq=3), "forecast_daily", daily, p.DAILY_SCHEMA)
except SystemExit as error:
    assert "lệch số dòng" in str(error)
else:
    raise AssertionError("lệch số dòng phải dừng")

print("PASS: forecast publish (14 dòng ETS sau mốc, khoảng bao dự báo, hệ số spend tính lại đúng mô hình, "
      "ghi đè JSONL, lệch số dòng thì dừng)")
