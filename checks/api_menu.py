"""Xem "menu" của Shopify Admin API: có những bảng gì, mỗi bảng có những cột gì. Chỉ hỏi cấu trúc, không lấy dữ liệu.

Giống SHOW TABLES / DESCRIBE trong SQL, nhưng hỏi qua API (GraphQL introspection), không chạm cơ sở dữ liệu của Shopify.

Chạy từ thư mục gốc:
  python checks/api_menu.py              # liệt kê mọi "bảng" hỏi được (giống SHOW TABLES)
  python checks/api_menu.py Order        # liệt kê "cột" của kiểu Order (giống DESCRIBE orders)
Mỗi lần chạy 1 lần gọi API, dùng token Shopify trong .env.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from pipelines.sources import shopify  # noqa: E402

TABLES = "{ __schema { queryType { fields { name description type { kind name ofType { name } } } } } }"
COLUMNS = """query t($name: String!) { __type(name: $name) { name fields(includeDeprecated: false) {
  name description type { kind name ofType { kind name ofType { kind name ofType { name } } } } } } }"""


def type_name(ref: dict) -> str:
    """NON_NULL/LIST → ghi gọn như String!, [LineItem]"""
    if ref["kind"] == "NON_NULL":
        return type_name(ref["ofType"]) + "!"
    if ref["kind"] == "LIST":
        return f"[{type_name(ref['ofType'])}]"
    return ref.get("name") or "?"


def short(text: str | None, width: int = 90) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= width else text[:width - 1] + "…"


def main(args: list[str]) -> None:
    if not args:
        fields = shopify.graphql(TABLES)["__schema"]["queryType"]["fields"]
        print(f"Shopify cho hỏi {len(fields)} điểm bắt đầu (giống SHOW TABLES):\n")
        for f in sorted(fields, key=lambda f: f["name"]):
            print(f"  {f['name']:<36} {short(f['description'])}")
        print("\nXem cột của một kiểu: python checks/api_menu.py Order")
        return
    found = shopify.graphql(COLUMNS, {"name": args[0]})["__type"]
    if not found:
        sys.exit(f"Không có kiểu {args[0]}. Tên kiểu viết hoa chữ đầu, ví dụ Order, LineItem, Product.")
    fields = found["fields"] or []
    print(f"Kiểu {found['name']} có {len(fields)} cột (giống DESCRIBE):\n")
    for f in fields:
        print(f"  {f['name']:<36} {type_name(f['type']):<28} {short(f['description'], 70)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
