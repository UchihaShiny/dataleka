"""Kiểm phần tính số của dashboard (dashboard/kpi.py). Không gọi BigQuery, không dùng khoá.

Chạy từ thư mục gốc:  python tests/test_dashboard.py
"""

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from dashboard import kpi  # noqa: E402

# Số thật 5–11/11 (đáp án câu 1, checks/sql/check_tuan4_dap_an.sql)
ROWS = [
    {"date": date(2026, 11, d), "rev": rev, "orders": o, "spend": sp, "cm_est": cm}
    for d, rev, o, sp, cm in [
        (5, 4567.60, 93, 3409.53, -294.43), (6, 6046.35, 98, 3336.44, 787.17), (7, 6366.77, 128, 3435.71, 906.43),
        (8, 6650.68, 112, 3453.74, 1082.02), (9, 6475.77, 121, 3143.38, 1273.10),
        (10, 6281.82, 126, 3744.46, 539.74), (11, 7857.91, 124, 3601.02, 1758.07),
    ]
]


def test_totals_from_sums():
    t = kpi.totals(ROWS)
    assert round(t["rev"], 2) == 44246.90 and round(t["spend"], 2) == 24124.28
    assert round(t["mer"], 2) == 1.83, "MER tính từ tổng"
    assert round(t["cm_est"], 2) == 6052.10
    mean_of_days = sum(r["rev"] / r["spend"] for r in ROWS) / len(ROWS)
    assert abs(t["mer"] - mean_of_days) > 0.001, "không được lấy trung bình MER từng ngày"


def test_missing_spend_blanks_cost_metrics():
    rows = ROWS[:2] + [dict(ROWS[2], spend=None, cm_est=None)]
    t = kpi.totals(rows)
    assert t["spend"] is None and t["mer"] is None and t["cpo"] is None and t["cm_est"] is None
    assert t["rev"] > 0 and t["aov"] is not None


def test_periods():
    end = date(2026, 11, 11)
    assert kpi.period("7 ngày", end) == (date(2026, 11, 5), end)
    assert kpi.period("Tháng này", end) == (date(2026, 11, 1), end)
    assert kpi.previous(date(2026, 11, 5), end) == (date(2026, 10, 29), date(2026, 11, 4))


def test_breakeven_and_change():
    assert round(kpi.breakeven_mer(), 2) == 1.47, "1 / (1 − 0,28 − 0,038)"
    assert kpi.change_pct(110, 100) == 10 and kpi.change_pct(5, 0) is None
    assert kpi.change_pct(-50, -100) == 50, "CM âm bớt lỗ là tăng"


def test_weeks_window():
    # 11/11/2026 là thứ Tư → thứ Bảy gần nhất 7/11; 8 tuần bắt đầu Chủ nhật 13/9 (khớp đáp án câu 5)
    assert kpi.weeks_window(date(2026, 11, 11), 8) == (date(2026, 9, 13), date(2026, 11, 7))
    assert kpi.weeks_window(date(2026, 11, 7), 1) == (date(2026, 11, 1), date(2026, 11, 7)), "thứ Bảy là chính nó"


def test_roas_flags_same_rule_as_mcp():
    rows = [{"product_line": "Long Sleeve", "rev": 17601.25, "spend": 11175.31},
            {"product_line": "Can Cooler", "rev": 73.99, "spend": 69.69},
            {"product_line": "Sát ngưỡng", "rev": 146.55, "spend": 100},          # 1,4655 < 1,4663 dù in ra 1,47
            {"product_line": "(không theo type)", "rev": 0, "spend": 96.91},
            {"product_line": "(không rõ)", "rev": 54.43, "spend": 0}]
    got = {r["product_line"]: r["status"] for r in kpi.roas_flags(rows, kpi.breakeven_mer())}
    assert got == {"Long Sleeve": "trên hoà vốn", "Can Cooler": "đang lỗ", "Sát ngưỡng": "đang lỗ",
                   "(không theo type)": "chưa gán type", "(không rõ)": "không có spend"}, got


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"  ✓ {name}")
    print("PASS")
