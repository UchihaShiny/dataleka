"""Bước 3 của khám phá dữ liệu: profile mẫu JSON trên máy, không gọi mạng.

Mỗi file data/explore/<nguồn>/<bảng>.json là một danh sách bản ghi (do explore_*.py ghi). Script duỗi JSON
lồng nhau thành đường dẫn trường (ví dụ `object_story_spec.link_data.call_to_action.type`, phần tử của
list ghi là `[]`), rồi cho từng đường dẫn: tỉ lệ bản ghi có giá trị, kiểu, số giá trị khác nhau, một ví dụ.
File bắt đầu bằng `_` là metadata của nguồn (danh sách trường), không profile.

Chạy từ thư mục gốc:  python checks/profile_sample.py            (mọi nguồn)
                      python checks/profile_sample.py meta       (một nguồn)
Kết quả: in tóm tắt, ghi data/explore/<nguồn>/profile.md.
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPLORE = ROOT / "data" / "explore"
MAX_DEPTH = 8
# Phòng hờ: không in ví dụ cho trường có thể là PII, dù script lấy mẫu đã không xin những trường này
PII = re.compile(r"(?i)(email|phone|address|first_?name|last_?name|zip|ip$|note)")


def save(source: str, name: str, records, folder: Path | None = None) -> Path:
    """Ghi mẫu của một bảng. Dùng chung cho explore_meta/shopify/klaviyo."""
    path = (folder or EXPLORE) / source / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    count = len(records) if isinstance(records, list) else 1
    print(f"  lưu data/explore/{source}/{path.name}: {count:,} bản ghi")
    return path


def flatten(value, prefix: str = "", depth: int = 0):
    """Sinh (đường dẫn, giá trị lá). Dict rỗng/list rỗng cũng là lá, để biết trường có mặt nhưng trống."""
    if isinstance(value, dict) and value and depth < MAX_DEPTH:
        for key, item in value.items():
            yield from flatten(item, f"{prefix}.{key}" if prefix else key, depth + 1)
    elif isinstance(value, list) and value and depth < MAX_DEPTH:
        for item in value:
            yield from flatten(item, f"{prefix}[]", depth + 1)
    else:
        yield prefix, value


def kind(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "số"
    if isinstance(value, str):
        if re.fullmatch(r"-?\d+(\.\d+)?", value):
            return "số dạng chuỗi"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}([T ].*)?", value):
            return "ngày giờ"
        return "chuỗi"
    if isinstance(value, dict):
        return "{} rỗng"
    if isinstance(value, list):
        return "[] rỗng"
    return type(value).__name__


def profile(records: list[dict]) -> list[dict]:
    """Mỗi đường dẫn một dòng: có giá trị ở bao nhiêu bản ghi, kiểu, số giá trị khác nhau, ví dụ."""
    present, kinds, values, example = defaultdict(set), defaultdict(set), defaultdict(set), {}
    for index, record in enumerate(records):
        for path, value in flatten(record):
            kinds[path].add(kind(value))
            if value in (None, "", [], {}):
                continue
            present[path].add(index)
            values[path].add(json.dumps(value, sort_keys=True, default=str)[:200])
            example.setdefault(path, value)
    rows = []
    for path in sorted(kinds):
        sample = example.get(path)
        shown = "(ẩn)" if PII.search(path.split(".")[-1].strip("[]")) else (
            "" if sample is None else str(sample).replace("\n", " ").replace("|", "/")[:60])
        rows.append({"path": path, "filled": len(present[path]), "total": len(records),
                     "kinds": ", ".join(sorted(kinds[path] - {"null"}) or ["null"]),
                     "distinct": len(values[path]), "example": shown})
    return rows


def report(source: str, folder: Path | None = None) -> str:
    folder = folder or EXPLORE
    lines = [f"# Profile mẫu: {source}", ""]
    for path in sorted((folder / source).glob("*.json")):
        if path.name.startswith("_"):
            continue
        records = json.loads(path.read_text(encoding="utf-8"))
        records = records if isinstance(records, list) else [records]
        rows = profile(records)
        lines += [f"## {path.stem} ({len(records):,} bản ghi, {len(rows)} trường)", "",
                  "| Trường | Có giá trị | Kiểu | Số giá trị khác | Ví dụ |", "|---|---|---|---|---|"]
        for row in rows:
            pct = 100 * row["filled"] / row["total"] if row["total"] else 0
            lines.append(f"| `{row['path']}` | {pct:.0f}% | {row['kinds']} | {row['distinct']} | {row['example']} |")
        lines.append("")
        empty = sum(1 for r in rows if r["filled"] == 0)
        print(f"  {source}/{path.stem}: {len(records):,} bản ghi, {len(rows)} trường, {empty} trường luôn trống")
    out = folder / source / "profile.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return str(out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sources = sys.argv[1:] or (sorted(p.name for p in EXPLORE.iterdir() if p.is_dir()) if EXPLORE.is_dir() else [])
    if not sources:
        sys.exit("Chưa có mẫu ở data/explore/. Chạy checks/explore_<nguồn>.py trước.")
    for name in sources:
        print(f"== {name} ==")
        print(f"  ghi {report(name)}")
