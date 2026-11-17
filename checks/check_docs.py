"""Đo độ phủ mô tả dbt cho silver + gold (tuần 4: AI phải hiểu schema).

Đọc 2 file dbt tạo ra trên máy, KHÔNG gọi BigQuery, không cần khoá:
- target/manifest.json: mô tả bảng và cột đã khai trong các file .yml (dbt build/parse ghi lại).
- target/catalog.json: cột THẬT của từng bảng trên BigQuery (chỉ có sau `python -m pipelines.dbt docs generate`).
Cột có trên BigQuery mà chưa khai trong .yml thì AI không có mô tả, đó là chỗ cần viết thêm.

Chạy: python -m checks.check_docs            (tóm tắt + danh sách thiếu)
      python -m checks.check_docs --all      (in cả cột đã có mô tả)
"""

import json
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "transform" / "target"
LAYERS = ("silver", "gold")


def load(name: str) -> dict:
    path = TARGET / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main(show_all: bool = False) -> int:
    manifest, catalog = load("manifest.json"), load("catalog.json")
    if not manifest:
        print("Chưa có transform/target/manifest.json: chạy python -m pipelines.dbt parse trước.")
        return 1
    real = {k: v for k, v in catalog.get("nodes", {}).items()}
    nodes = [n for n in manifest["nodes"].values()
             if n["resource_type"] in ("model", "seed") and n.get("schema") in LAYERS]
    totals = {"bang": 0, "bang_co_mo_ta": 0, "cot": 0, "cot_co_mo_ta": 0, "bq_bang": 0, "bq_cot": 0}
    no_catalog = []
    for n in sorted(nodes, key=lambda x: (x["schema"], x["name"])):
        declared = {c.lower(): (v.get("description") or "").strip() for c, v in n["columns"].items()}
        cat = real.get(n["unique_id"])
        if cat is None:
            no_catalog.append(n["name"])
            cols = list(declared)  # không biết cột thật: chỉ đếm cột đã khai
        else:
            cols = [c.lower() for c in cat["columns"]]
        missing = [c for c in cols if not declared.get(c)]
        extra = [c for c in declared if cat is not None and c not in cols]  # khai mà bảng không có: mô tả sai tên
        has_desc = bool((n.get("description") or "").strip())
        if cat is not None:  # mô tả THẬT trên BigQuery (persist_docs đẩy lên lúc build), đọc từ catalog
            totals["bq_bang"] += bool(((cat.get("metadata") or {}).get("comment") or "").strip())
            totals["bq_cot"] += sum(bool((c.get("comment") or "").strip()) for c in cat["columns"].values())
        totals["bang"] += 1
        totals["bang_co_mo_ta"] += has_desc
        totals["cot"] += len(cols)
        totals["cot_co_mo_ta"] += len(cols) - len(missing)
        flag = "" if cat is not None else "  (chưa có trong catalog: chỉ đếm cột đã khai)"
        print(f"{n['schema']}.{n['name']}: bảng {'có' if has_desc else 'THIẾU'} mô tả, "
              f"cột {len(cols) - len(missing)}/{len(cols)}{flag}")
        if missing:
            print(f"    thiếu: {', '.join(missing)}")
        if extra:
            print(f"    khai nhưng bảng không có: {', '.join(extra)}")
        if show_all:
            for c in cols:
                if declared.get(c):
                    print(f"    {c}: {declared[c][:90]}")
    pct = lambda a, b: f"{100 * a / b:.0f}%" if b else "-"
    print(f"\nTổng: bảng có mô tả {totals['bang_co_mo_ta']}/{totals['bang']} "
          f"({pct(totals['bang_co_mo_ta'], totals['bang'])}), "
          f"cột có mô tả {totals['cot_co_mo_ta']}/{totals['cot']} ({pct(totals['cot_co_mo_ta'], totals['cot'])})")
    if catalog:
        print(f"Trên BigQuery (catalog, sinh lúc {catalog['metadata']['generated_at'][:19]} UTC): "
              f"bảng có mô tả {totals['bq_bang']}/{totals['bang']}, cột {totals['bq_cot']}/{totals['cot']}. "
              "Thấp hơn dòng trên = chưa build sau khi sửa .yml, hoặc catalog sinh trước build.")
    if no_catalog:
        print(f"Catalog thiếu {len(no_catalog)} bảng ({', '.join(no_catalog)}): số cột của các bảng này CHƯA đủ. "
              "Chạy python -m pipelines.dbt docs generate rồi chạy lại script này.")
    return 0


if __name__ == "__main__":
    sys.exit(main("--all" in sys.argv))
