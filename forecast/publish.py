"""Mô hình 8, phần B, bước 3: GHI DỰ BÁO vào gold (chạy mỗi tuần, sau dbt build). Ghi đè cả bảng (WRITE_TRUNCATE),
hợp với BigQuery Sandbox (không DML, không MERGE).

  gold.forecast_daily        : ETS dự báo orders 14 ngày tới (Huy Anh chốt 12/11: chỉ 14 ngày, phần đã kiểm),
                               khoảng 80% đã nhân k (k_cuoi ước lại từ backtest MỚI NHẤT mỗi lần chạy).
  gold.forecast_spend_model  : 1 dòng, hệ số spend_reg (log đơn ~ log spend + thứ, 56 ngày cuối) để tool MCP tính
                               kịch bản "nếu chi X USD/ngày trong 14 ngày tới". Kèm khoảng spend đã thấy: ngoài
                               khoảng đó tool không đưa số.
Mỗi dòng ghi kèm WAPE và độ phủ backtest để ai đọc cũng biết số chắc tới đâu.
Giới hạn: bảng bị ghi đè nên KHÔNG giữ bản dự báo cũ (cần chốt với anh Quang chỗ lưu); backtest là bằng chứng độ
chính xác thay thế.

Chạy từ thư mục gốc (khoá GCP, CÓ GHI 2 bảng gold):  python -m forecast.publish
"""

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from forecast import backtest as b

DAYS = b.HORIZON   # 14

DAILY_SCHEMA = [
    ("run_at", "TIMESTAMP"), ("origin", "DATE"), ("date", "DATE"), ("h", "INT64"), ("weekday", "STRING"),
    ("model", "STRING"), ("fc", "FLOAT64"), ("lo", "FLOAT64"), ("hi", "FLOAT64"), ("k", "FLOAT64"),
    ("train_from", "DATE"), ("train_to", "DATE"), ("backtest_wape_pct", "FLOAT64"), ("backtest_cover_pct", "FLOAT64"),
    ("backtest_total_p80_pct", "FLOAT64"), ("backtest_total_bias_pct", "FLOAT64"),
]
SPEND_SCHEMA = [
    ("run_at", "TIMESTAMP"), ("origin", "DATE"), ("intercept", "FLOAT64"), ("b_log_spend", "FLOAT64"),
    ("dow_tue", "FLOAT64"), ("dow_wed", "FLOAT64"), ("dow_thu", "FLOAT64"), ("dow_fri", "FLOAT64"),
    ("dow_sat", "FLOAT64"), ("dow_sun", "FLOAT64"), ("sigma", "FLOAT64"), ("t80", "FLOAT64"), ("k", "FLOAT64"),
    ("spend_min", "FLOAT64"), ("spend_max", "FLOAT64"), ("spend_7d_mean", "FLOAT64"), ("n_days", "INT64"),
    ("train_from", "DATE"), ("train_to", "DATE"), ("backtest_wape_pct", "FLOAT64"), ("backtest_cover_pct", "FLOAT64"),
    ("backtest_total_p80_pct", "FLOAT64"), ("backtest_total_bias_pct", "FLOAT64"),
]


def build(df: pd.DataFrame, run_at: datetime) -> tuple[list[dict], list[dict], dict]:
    """Trả (dòng forecast_daily, dòng forecast_spend_model, tóm tắt). Không đụng BigQuery."""
    import statsmodels.api as sm

    df = df.sort_index()
    bt = b.backtest(df)
    scores = b.score(bt).set_index(["model", "tam_xa"])
    cal = b.calibration_table(bt).set_index("model")
    tot = b.total_table(bt).set_index("model")
    origin = df.index[-1]
    run = run_at.isoformat()

    # ETS 14 ngày, khoảng nhân k
    k_ets = float(cal.loc["ets", "k_cuoi"])
    future = pd.DataFrame(index=pd.date_range(origin + pd.Timedelta(days=1), periods=DAYS, freq="D"))
    fc = b.f_ets(df, future)
    m = fc["mean"].clip(lower=0.5)
    lo = m * (fc["lo"].clip(lower=0.5) / m) ** k_ets
    hi = m * (fc["hi"].clip(lower=0.5) / m) ** k_ets
    train = df.index[-b.TRAIN_DAYS:]
    daily = [{
        "run_at": run, "origin": str(origin.date()), "date": str(d.date()), "h": h, "weekday": d.strftime("%a"),
        "model": "ets", "fc": round(float(m.loc[d]), 2), "lo": round(float(lo.loc[d]), 2),
        "hi": round(float(hi.loc[d]), 2), "k": k_ets, "train_from": str(train[0].date()), "train_to": str(train[-1].date()),
        "backtest_wape_pct": float(scores.loc[("ets", "1–14"), "wape_pct"]),
        "backtest_cover_pct": float(cal.loc["ets", "phu_chinh_pct"]),
        "backtest_total_p80_pct": float(tot.loc["ets", "p80_abs_pct"]),
        "backtest_total_bias_pct": float(tot.loc["ets", "bias_pct"]),
    } for h, d in enumerate(future.index, start=1)]

    # hệ số spend_reg (cùng cách học như backtest.f_spend_reg)
    tr = df.iloc[-b.REG_DAYS:]
    tr = tr[(tr["spend"] > 0) & (tr["orders"] > 0)]
    fit = sm.OLS(np.log(tr["orders"].to_numpy(dtype=float)), b._design(tr)).fit()
    p = fit.params
    from scipy import stats

    spend = [{
        "run_at": run, "origin": str(origin.date()), "intercept": float(p[0]), "b_log_spend": float(p[1]),
        **{f"dow_{n}": float(p[2 + i]) for i, n in enumerate(["tue", "wed", "thu", "fri", "sat", "sun"])},
        "sigma": float(np.sqrt(fit.scale)), "t80": float(stats.t.ppf(1 - b.ALPHA / 2, fit.df_resid)),
        "k": float(cal.loc["spend_reg", "k_cuoi"]),
        "spend_min": round(float(tr["spend"].min()), 2), "spend_max": round(float(tr["spend"].max()), 2),
        "spend_7d_mean": round(float(df["spend"].iloc[-7:].mean()), 2), "n_days": int(len(tr)),
        "train_from": str(tr.index[0].date()), "train_to": str(tr.index[-1].date()),
        "backtest_wape_pct": float(scores.loc[("spend_reg", "1–14"), "wape_pct"]),
        "backtest_cover_pct": float(cal.loc["spend_reg", "phu_chinh_pct"]),
        "backtest_total_p80_pct": float(tot.loc["spend_reg", "p80_abs_pct"]),
        "backtest_total_bias_pct": float(tot.loc["spend_reg", "bias_pct"]),
    }]
    summary = {"origin": str(origin.date()), "k_ets": k_ets, "k_spend": spend[0]["k"],
               "ets_14d_total": round(float(m.sum()), 0), "b_log_spend": round(spend[0]["b_log_spend"], 3)}
    return daily, spend, summary


def write(bq, table: str, rows: list[dict], schema: list[tuple]) -> int:
    from google.cloud import bigquery

    table_id = f"{bq.project}.gold.{table}"
    config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema=[bigquery.SchemaField(n, t, mode="REQUIRED") for n, t in schema],
    )
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / f"{table}.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        with path.open("rb") as handle:
            bq.load_table_from_file(handle, table_id, job_config=config).result()
    n = bq.get_table(table_id).num_rows
    print(f"  {table_id}: {len(rows)} dòng gửi, {n} dòng trong BigQuery")
    if n != len(rows):
        sys.exit(f"LỖI: {table_id} lệch số dòng ({len(rows)} so với {n})")
    return n


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    from pipelines.bq import client

    df = b.load_bigquery()
    print(f"Dữ liệu {df.index.min().date()} → {df.index.max().date()} ({len(df)} ngày). Đang chạy backtest để ước k...")
    daily, spend, summary = build(df, datetime.now(timezone.utc))
    print(f"Mốc {summary['origin']}: ETS 14 ngày tổng ~{summary['ets_14d_total']:.0f} đơn, k_ets {summary['k_ets']}, "
          f"k_spend {summary['k_spend']}, hệ số log spend {summary['b_log_spend']}")
    bq = client()
    write(bq, "forecast_daily", daily, DAILY_SCHEMA)
    write(bq, "forecast_spend_model", spend, SPEND_SCHEMA)


if __name__ == "__main__":
    main()
