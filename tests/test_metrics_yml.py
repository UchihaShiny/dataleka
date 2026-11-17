"""Kiểm transform/metrics.yml: mỗi chỉ số đủ trường, và cột nguồn có thật trong mô tả dbt (_marts.yml).

Vì sao: metrics.yml viết tay. Đổi tên cột trong dbt mà quên sửa file này thì định nghĩa trỏ vào cột không còn,
test này báo ngay. Không cần BigQuery. Chạy: python tests/test_metrics_yml.py
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
metrics = yaml.safe_load((ROOT / "transform" / "metrics.yml").read_text(encoding="utf-8"))
marts = yaml.safe_load((ROOT / "transform" / "models" / "marts" / "_marts.yml").read_text(encoding="utf-8"))
columns = {m["name"]: {c["name"] for c in m.get("columns", [])} for m in marts["models"]}
# bảng dự báo không do dbt dựng (forecast/publish.py ghi), khai báo là source schema gold trong _sources.yml
sources = yaml.safe_load((ROOT / "transform" / "models" / "staging" / "_sources.yml").read_text(encoding="utf-8"))
for src in sources["sources"]:
    if src.get("schema") == "gold":
        columns.update({t["name"]: {c["name"] for c in t.get("columns", [])} for t in src["tables"]})

# 1. Đủ chỉ số brief tuần 3 (Rev, Orders, AOV, Spend, MER, CPO, CM ước + theo type)
need = {"rev", "orders", "aov", "spend", "mer", "cpo", "cm_est", "rev_type", "spend_type", "roas_type"}
assert need <= set(metrics["metrics"]), need - set(metrics["metrics"])

for name, m in metrics["metrics"].items():
    # 2. Đủ trường, có ít nhất 1 bẫy
    for field in ("label", "formula", "source", "grain", "sum_rule", "traps"):
        assert m.get(field), f"{name} thiếu {field}"
    # 3. Nguồn dạng bảng.cột, bảng và cột có trong _marts.yml
    table, _, column = m["source"].partition(".")
    assert table in columns, f"{name}: bảng {table} không có trong _marts.yml"
    assert column in columns[table], f"{name}: cột {table}.{column} không có trong _marts.yml"
    # 3b. Mỗi bẫy phải là CÂU CHỮ. Dấu ": " giữa câu làm YAML âm thầm đọc thành dict (gặp 12/11, mô hình cohort).
    assert all(isinstance(t, str) for t in m["traps"]), f"{name}: bẫy bị đọc thành dict, bỏ dấu ': ' giữa câu"
    for field in ("label", "formula", "source", "grain", "sum_rule"):
        assert isinstance(m[field], str), f"{name}.{field} không phải chữ"
    # 4. sum_rule chỉ 2 kiểu
    assert m["sum_rule"].startswith(("cộng", "từ tổng")), f"{name}: sum_rule lạ {m['sum_rule']}"

# 5. Tỉ lệ CM trong công thức khớp vars dbt_project.yml (một chỗ sửa, không lệch)
project = yaml.safe_load((ROOT / "transform" / "dbt_project.yml").read_text(encoding="ascii"))
for var in ("cogs_rate", "fee_rate"):
    assert str(project["vars"][var]).replace(".", ",") in metrics["metrics"]["cm_est"]["formula"], var

print(f"test_metrics_yml: PASS ({len(metrics['metrics'])} chỉ số)")
