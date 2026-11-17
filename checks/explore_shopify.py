"""Khám phá schema Shopify trên 1 ngày mẫu. Chỉ đọc (query), không ghi BigQuery, không lấy PII.

Bước 1, Shopify tự mô tả: GraphQL introspection `__type(name: ...)` cho Order, LineItem, Refund, Product,
ProductVariant, Customer → tên, kiểu, mô tả của mọi trường. Lưu ở data/explore/shopify/_schema_<Type>.json.
Bước 2, mẫu thật: đơn tạo trong ngày (giờ Phoenix) kèm line item, refund; sản phẩm và variant sửa trong ngày.
Câu truy vấn tự dựng từ bước 1: lấy mọi trường scalar/enum không cần tham số và mọi trường tiền (MoneyBag),
**bỏ trường có thể là PII** (email, phone, note, address, IP, customer). Trường nào Shopify chặn (thiếu
quyền) thì bỏ, ghi vào _dropped.json, gọi lại.

Khoảng 10–15 lần gọi, đọc điểm truy vấn như pipeline.
Chạy từ thư mục gốc:  python checks/explore_shopify.py [--day 2026-11-07]
Sau đó:  python checks/profile_sample.py shopify
"""

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "checks"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from pipelines.sources import shopify  # noqa: E402
from profile_sample import save  # noqa: E402

TYPES = ["Order", "LineItem", "Refund", "Product", "ProductVariant", "Customer"]
PII = re.compile(r"(?i)(email|phone|note|address|customer|clientip|browserip|^ip$|firstname|lastname|"
                 r"displayname|billing|shipping(?!line)|marketing|sms|location)")
PAGE, LINES, MAX_PAGES = 25, 10, 10
INTROSPECT = """
query t($name: String!) { __type(name: $name) { name description fields(includeDeprecated: false) {
  name description
  args { name type { kind } }
  type { kind name ofType { kind name ofType { kind name ofType { kind name } } } }
} } }
"""


def base(type_ref: dict) -> tuple[str, str]:
    """Bóc NON_NULL/LIST: trả (kind, name) của kiểu lõi."""
    while type_ref.get("ofType"):
        type_ref = type_ref["ofType"]
    return type_ref["kind"], type_ref.get("name")


def selection(described: dict) -> list[str]:
    """Các trường lấy được thẳng: scalar/enum (cả list), MoneyBag → shopMoney; bỏ trường cần tham số và PII."""
    picked = []
    for field in described.get("fields") or []:
        name = field["name"]
        if PII.search(name) or any(a["type"]["kind"] == "NON_NULL" for a in field.get("args") or []):
            continue
        kind, type_name = base(field["type"])
        if kind in ("SCALAR", "ENUM"):
            picked.append(name)
        elif type_name == "MoneyBag":
            picked.append(f"{name} {{ shopMoney {{ amount currencyCode }} }}")
    return picked


ROOT_KIND = {"orders": "Order", "products": "Product", "productVariants": "ProductVariant"}


def blocked(error: dict) -> tuple[str, str] | None:
    """(kiểu, trường) mà Shopify báo lỗi (thường ACCESS_DENIED), đọc từ `path` của lỗi."""
    path = [p for p in error.get("path") or [] if isinstance(p, str)]
    if len(path) < 2:
        return None
    kind = "LineItem" if "lineItems" in path else "Refund" if "refunds" in path else ROOT_KIND.get(path[0])
    return (kind, path[-1]) if kind else None


def run(build, fields: dict[str, list[str]], dropped: list, label: str) -> dict:
    """Gọi query build(fields); trường bị chặn thì bỏ khỏi đúng kiểu rồi gọi lại (tối đa 20 lần)."""
    for _ in range(20):
        body = shopify.graphql_body(build(fields))
        errors = body.get("errors") or []
        if not errors:
            return body["data"]
        removed = False
        for error in errors:
            hit = blocked(error)
            names = fields.get(hit[0], []) if hit else []
            full = next((f for f in names if f.split(" ")[0] == hit[1]), None) if hit else None
            if full:
                names.remove(full)
                dropped.append({"where": f"{label}.{hit[0]}", "field": hit[1], "reason": error.get("message", "")[:200]})
                print(f"  {label}: Shopify chặn {hit[0]}.{hit[1]}, bỏ rồi gọi lại")
                removed = True
        if not removed:
            sys.exit(f"Shopify báo lỗi khi lấy {label}: {errors[0].get('message')}")
    sys.exit(f"{label}: bỏ quá 20 lần vẫn lỗi, dừng.")


def window(day: date) -> str:
    """Mốc giờ đầy đủ có offset Phoenix (bài học: `created_at:<ngày` tính cả ngày đó)."""
    return (f"'{day}T00:00:00-07:00'", f"'{day + timedelta(days=1)}T00:00:00-07:00'")


def pages(build, fields, dropped, label, root: str) -> list[dict]:
    nodes, after = [], None
    for _ in range(MAX_PAGES):
        data = run(lambda f: build(f, after), fields, dropped, label)[root]
        nodes.extend(data["nodes"])
        if not data["pageInfo"]["hasNextPage"]:
            break
        after = data["pageInfo"]["endCursor"]
    return nodes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", type=date.fromisoformat, default=date(2026, 11, 7))
    args = parser.parse_args()
    start, end = window(args.day)

    print("== Bước 1: Shopify tự mô tả ==")
    described = {}
    for name in TYPES:
        described[name] = shopify.graphql(INTROSPECT, {"name": name})["__type"] or {}
        save("shopify", f"_schema_{name}", described[name])
        print(f"  {name}: {len(described[name].get('fields') or [])} trường")
    fields = {name: selection(described[name]) for name in ["Order", "LineItem", "Refund", "Product",
                                                              "ProductVariant"]}
    print("  sẽ lấy: " + ", ".join(f"{k} {len(v)}" for k, v in fields.items()) + " trường (đã bỏ PII)")

    print(f"== Bước 2: mẫu ngày {args.day} (giờ Phoenix) ==")
    dropped: list = []

    def orders_query(f, after):
        cursor = f', after: "{after}"' if after else ""
        return (f'{{ orders(first: {PAGE}{cursor}, query: "created_at:>={start} AND created_at:<{end}") {{ '
                f'pageInfo {{ hasNextPage endCursor }} nodes {{ {" ".join(f["Order"])} '
                f'refunds {{ {" ".join(f["Refund"])} }} '
                f'lineItems(first: {LINES}) {{ nodes {{ {" ".join(f["LineItem"])} variant {{ id }} product {{ id }} }} }} '
                f'}} }} }}')

    orders = pages(orders_query, fields, dropped, "orders", "orders")
    lines, refunds = [], []
    for order in orders:
        for line in (order.pop("lineItems", None) or {}).get("nodes", []):
            lines.append({"order_id": order["id"], **line})
        for refund in order.pop("refunds", None) or []:
            refunds.append({"order_id": order["id"], **refund})
    save("shopify", "orders", orders)
    save("shopify", "line_items", lines)
    save("shopify", "refunds", refunds)

    def products_query(f, after):
        cursor = f', after: "{after}"' if after else ""
        return (f'{{ products(first: {PAGE}{cursor}, query: "updated_at:>={start} AND updated_at:<{end}") {{ '
                f'pageInfo {{ hasNextPage endCursor }} nodes {{ {" ".join(f["Product"])} }} }} }}')

    def variants_query(f, after):
        cursor = f', after: "{after}"' if after else ""
        return (f'{{ productVariants(first: {PAGE}{cursor}, query: "updated_at:>={start} AND updated_at:<{end}") {{ '
                f'pageInfo {{ hasNextPage endCursor }} nodes {{ {" ".join(f["ProductVariant"])} product {{ id }} }} }} }}')

    save("shopify", "products", pages(products_query, fields, dropped, "products", "products"))
    save("shopify", "variants", pages(variants_query, fields, dropped, "variants", "productVariants"))
    save("shopify", "_dropped", dropped)
    shopify.tracker.save(check="explore", day=args.day)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
