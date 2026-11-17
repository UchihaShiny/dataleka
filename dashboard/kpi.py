"""Phần tính số của dashboard, tách khỏi giao diện để test được không cần BigQuery.

Quy ước giống server MCP datae và metrics.yml:
- ngày = ngày kinh doanh America/Phoenix; chỉ tính tới gold.load_status.complete_through (ngày trọn theo lúc nạp);
- MER, AOV, CPO tính từ TỔNG của kỳ, không lấy trung bình từng ngày;
- CM ước = rev × (1 − cogs_rate − fee_rate) − spend, tỉ lệ đọc từ transform/dbt_project.yml (tạm 28% và 3,8%).
"""

import re
import math
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRESETS = {"7 ngày": 7, "14 ngày": 14, "28 ngày": 28, "Tháng này": 0}


def rates() -> tuple[float, float]:
    """cogs_rate, fee_rate từ dbt_project.yml (1 chỗ định nghĩa, không chép số)."""
    text = (ROOT / "transform" / "dbt_project.yml").read_text(encoding="ascii")
    get = lambda name: float(re.search(rf"^\s*{name}:\s*([0-9.]+)", text, re.M).group(1))
    return get("cogs_rate"), get("fee_rate")


def breakeven_mer() -> float:
    """MER hoà vốn: CM = 0 khi rev × (1 − cogs − fee) = spend."""
    cogs, fee = rates()
    return 1 / (1 - cogs - fee)


def period(preset: str, end: date) -> tuple[date, date]:
    days = PRESETS[preset]
    start = end.replace(day=1) if days == 0 else end - timedelta(days=days - 1)
    return start, end


def previous(start: date, end: date) -> tuple[date, date]:
    """Kỳ trước cùng số ngày, liền trước kỳ chọn."""
    n = (end - start).days + 1
    return start - timedelta(days=n), start - timedelta(days=1)


def _div(a, b):
    return a / b if known(a) and known(b) and b else None


def known(value):
    return value is not None and math.isfinite(float(value))


def totals(rows: list[dict]) -> dict:
    """7 chỉ số brief cho cả kỳ. spend null ở ngày nào thì MER, CPO, CM ước của kỳ là None (không biết chi phí)."""
    rev = sum(float(r["rev"]) for r in rows) if rows and all(known(r["rev"]) for r in rows) else None
    orders = sum(int(r["orders"]) for r in rows) if rows and all(known(r["orders"]) for r in rows) else None
    has_spend = bool(rows) and all(known(r["spend"]) for r in rows)
    spend = sum(float(r["spend"]) for r in rows) if has_spend else None
    cm = sum(float(r["cm_est"]) for r in rows) if has_spend and all(known(r["cm_est"]) for r in rows) else None
    return {
        "rev": rev, "orders": orders, "aov": _div(rev, orders), "spend": spend,
        "mer": _div(rev, spend) if spend is not None else None,
        "cpo": _div(spend, orders) if spend is not None else None,
        "cm_est": cm, "days": len(rows),
    }


def weeks_window(end: date, n: int = 12) -> tuple[date, date]:
    """n tuần TRỌN (Chủ nhật → thứ Bảy) kết thúc ở thứ Bảy gần nhất ≤ end, cho biểu đồ xu hướng theo tuần."""
    sat = end - timedelta(days=(end.weekday() - 5) % 7)     # Python: thứ Hai = 0, thứ Bảy = 5
    return sat - timedelta(days=7 * n - 1), sat


UNTYPED = "(không theo type)"


def roas_flags(rows: list[dict], breakeven: float) -> list[dict]:
    """ROAS theo type, cùng quy tắc với MCP type_performance: tính từ tổng, so ngưỡng bằng số CHƯA làm tròn,
    '(không theo type)' không phải type lỗ (spend chưa gán type, rev của nó nằm ở type khác)."""
    out = []
    for r in rows:
        rev = float(r["rev"]) if known(r.get("rev")) else None
        spend = float(r["spend"]) if known(r.get("spend")) else None
        roas = _div(rev, spend)
        if r["product_line"] == UNTYPED:
            status = "chưa gán type"
        elif rev is None or spend is None:
            status = "chưa đủ dữ liệu"
        elif roas is None:
            status = "không có spend"
        else:
            status = "đang lỗ" if roas < breakeven else "trên hoà vốn"
        out.append({"product_line": r["product_line"], "rev": rev, "spend": spend, "roas": roas, "status": status})
    return out


def change_pct(now, before):
    if now is None or before is None or before == 0:
        return None
    return 100 * (now - before) / abs(before)
