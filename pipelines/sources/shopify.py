"""Nguồn dlt cho Shopify: orders, line items, refunds, products, variants. Chỉ đọc.

Dùng bulk operation của Admin GraphQL: Shopify chạy truy vấn ở chế độ nền rồi trả 1 file JSONL,
nên lấy được hết lịch sử mà không vướng giới hạn chi phí khi phân trang. bulkOperationRunQuery là
mutation nhưng chỉ tạo một job đọc, không sửa đơn hay sản phẩm.

PII (email, tên, SĐT, địa chỉ) chỉ nằm trong bảng pii_customers; bảng orders giữ customer_key là
sha256 của email đã chuẩn hoá.

Incremental theo updated_at (brief): lần đầu lấy full từ 2024-11-01; các lần sau bulk chỉ lấy đơn có
updated_at từ mốc mới nhất đang có trong BigQuery trừ 1 ngày, rồi gộp vào bản hiện có theo order_id
(thay cả line items, refunds của đơn đó). Bản hiện có đọc thẳng từ BigQuery bằng list_rows (không tốn
quota truy vấn), không lưu trên máy để PII không nằm trên máy cá nhân.
"""

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import dlt
import requests

from pipelines.limits import Tracker

POLL_SECONDS = 5
MIN_AVAILABLE = 0.2  # còn dưới 20% điểm truy vấn thì chờ cho hồi
tracker = Tracker("shopify")
TIMEOUT_SECONDS = 1800

ORDERS_QUERY = """
{
  orders(query: "%(filter)s") {
    edges { node {
      id name email phone createdAt processedAt updatedAt cancelledAt cancelReason closedAt test
      displayFinancialStatus displayFulfillmentStatus currencyCode sourceName tags discountCodes
      subtotalPriceSet { shopMoney { amount } }
      currentSubtotalPriceSet { shopMoney { amount } }
      totalPriceSet { shopMoney { amount } }
      currentTotalPriceSet { shopMoney { amount } }
      totalDiscountsSet { shopMoney { amount } }
      currentTotalDiscountsSet { shopMoney { amount } }
      totalShippingPriceSet { shopMoney { amount } }
      totalTaxSet { shopMoney { amount } }
      currentTotalTaxSet { shopMoney { amount } }
      totalRefundedSet { shopMoney { amount } }
      customer { id firstName lastName }
      shippingAddress { name address1 address2 city province zip countryCodeV2 phone }
      refunds { id createdAt totalRefundedSet { shopMoney { amount } } }
      lineItems { edges { node {
        id sku name title variantTitle vendor quantity currentQuantity
        originalUnitPriceSet { shopMoney { amount } }
        originalTotalSet { shopMoney { amount } }
        discountedTotalSet { shopMoney { amount } }
        totalDiscountSet { shopMoney { amount } }
        discountedUnitPriceAfterAllDiscountsSet { shopMoney { amount } }
        priceAfterAllDiscountsBeforeTaxesSet { shopMoney { amount } }
        variant { id }
        product { id productType }
      } } }
    } }
  }
}
"""

PRODUCTS_QUERY = """
{
  products {
    edges { node {
      id title handle productType vendor tags status createdAt updatedAt
      variants { edges { node { id sku title price createdAt updatedAt selectedOptions { name value } } } }
    } }
  }
}
"""


def settings() -> tuple[str, str, str]:
    names = ["SHOPIFY_SHOP_DOMAIN", "SHOPIFY_ACCESS_TOKEN", "SHOPIFY_API_VERSION"]
    env = {name: os.environ.get(name, "").strip() for name in names}
    missing = [name for name, value in env.items() if not value]
    if missing:
        sys.exit(f"Thiếu trong .env: {', '.join(missing)}")
    domain = re.sub(r"^https?://", "", env["SHOPIFY_SHOP_DOMAIN"]).split("/")[0]
    return domain, env["SHOPIFY_ACCESS_TOKEN"], env["SHOPIFY_API_VERSION"]


def graphql(query: str, variables: dict | None = None) -> dict:
    """Gọi Admin GraphQL, có lỗi là dừng. Token chỉ nằm trong header, không in ra."""
    body = graphql_body(query, variables)
    if body.get("errors"):
        sys.exit(f"Shopify báo lỗi: {body['errors'][0].get('message')}")
    return body["data"]


def graphql_body(query: str, variables: dict | None = None) -> dict:
    """Trả nguyên phản hồi, kể cả `errors` theo từng trường (script khám phá cần đọc để bỏ trường bị chặn)."""
    domain, token, version = settings()
    tracker.call()
    response = requests.post(
        f"https://{domain}/admin/api/{version}/graphql.json",
        json={"query": query, "variables": variables or {}},
        headers={"X-Shopify-Access-Token": token},
        timeout=60,
    )
    if response.status_code != 200:
        sys.exit(f"Shopify trả HTTP {response.status_code}")
    body = response.json()
    throttle(body)
    return body


def throttle(body: dict) -> None:
    """Shopify tính điểm kiểu xô rò: đọc điểm còn lại, dưới 20% thì chờ cho hồi tới 50%."""
    status = ((body.get("extensions") or {}).get("cost") or {}).get("throttleStatus")
    if not status:
        return
    maximum, available, rate = (float(status["maximumAvailable"]), float(status["currentlyAvailable"]),
                                float(status["restoreRate"]))
    tracker.seen(100 * (1 - available / maximum))
    if available < MIN_AVAILABLE * maximum and rate > 0:
        wait = (0.5 * maximum - available) / rate
        print(f"  Shopify còn {available:.0f}/{maximum:.0f} điểm, chờ {wait:.0f} giây")
        tracker.waited(wait)
        time.sleep(wait)


def bulk_lines(query: str) -> list[dict]:
    """Chạy một bulk query, chờ xong, tải file JSONL kết quả."""
    data = graphql(
        "mutation run($q: String!) { bulkOperationRunQuery(query: $q, groupObjects: false) "
        "{ bulkOperation { id status } userErrors { field message } } }",
        {"q": query},
    )["bulkOperationRunQuery"]
    if data["userErrors"]:
        sys.exit(f"Shopify từ chối bulk query: {data['userErrors']}")
    operation_id = data["bulkOperation"]["id"]
    started = time.monotonic()
    while True:
        operation = graphql(
            "query op($id: ID!) { bulkOperation(id: $id) { status errorCode objectCount url } }",
            {"id": operation_id},
        )["bulkOperation"]
        status = operation["status"]
        print(f"  bulk {status}, {operation.get('objectCount') or 0} object")
        if status == "COMPLETED":
            break
        if status in ("FAILED", "CANCELED", "EXPIRED"):
            sys.exit(f"Bulk operation {status}: {operation.get('errorCode')}")
        if time.monotonic() - started > TIMEOUT_SECONDS:
            sys.exit("Bulk operation chạy quá 30 phút, dừng.")
        time.sleep(POLL_SECONDS)
    if not operation["url"]:
        return []
    download = requests.get(operation["url"], timeout=300)
    download.raise_for_status()
    return [json.loads(line) for line in download.text.splitlines() if line.strip()]


def money(value: dict | None) -> Decimal | None:
    if not value or not value.get("shopMoney"):
        return None
    return Decimal(value["shopMoney"]["amount"])


def stamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def customer_key(email: str | None) -> str | None:
    """Khoá nối khách giữa các bảng mà không lộ email."""
    if not email or not email.strip():
        return None
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def kind(gid: str) -> str:
    """gid://shopify/LineItem/123 → LineItem"""
    return gid.split("/")[3]


def split_orders(lines: list[dict]) -> tuple[list, list, list, dict]:
    """Tách file bulk thành orders, line items, refunds và khách (PII)."""
    orders, items, refunds, customers = [], [], [], {}
    for line in lines:
        if kind(line["id"]) == "Order":
            customer = line.get("customer") or {}
            address = line.get("shippingAddress") or {}
            key = customer_key(line.get("email"))
            orders.append({
                "order_id": line["id"],
                "order_name": line["name"],
                "customer_id": customer.get("id"),
                "customer_key": key,
                "created_at": stamp(line["createdAt"]),
                "processed_at": stamp(line.get("processedAt")),
                "updated_at": stamp(line["updatedAt"]),
                "cancelled_at": stamp(line.get("cancelledAt")),
                "cancel_reason": line.get("cancelReason"),
                "closed_at": stamp(line.get("closedAt")),
                "is_test": line.get("test"),
                "financial_status": line.get("displayFinancialStatus"),
                "fulfillment_status": line.get("displayFulfillmentStatus"),
                "currency": line.get("currencyCode"),
                "source_name": line.get("sourceName"),
                "tags": ",".join(line.get("tags") or []),
                "discount_codes": ",".join(line.get("discountCodes") or []),
                "subtotal": money(line.get("subtotalPriceSet")),
                "current_subtotal": money(line.get("currentSubtotalPriceSet")),
                "total_price": money(line.get("totalPriceSet")),
                "current_total": money(line.get("currentTotalPriceSet")),
                "total_discounts": money(line.get("totalDiscountsSet")),
                "current_total_discounts": money(line.get("currentTotalDiscountsSet")),
                "total_shipping": money(line.get("totalShippingPriceSet")),
                "total_tax": money(line.get("totalTaxSet")),
                "current_total_tax": money(line.get("currentTotalTaxSet")),
                "total_refunded": money(line.get("totalRefundedSet")),
                "shipping_country": address.get("countryCodeV2"),
                "shipping_province": address.get("province"),
            })
            for refund in line.get("refunds") or []:
                refunds.append({
                    "refund_id": refund["id"],
                    "order_id": line["id"],
                    "created_at": stamp(refund.get("createdAt")),
                    "total_refunded": money(refund.get("totalRefundedSet")),
                })
            if key:
                # Một khách có thể có nhiều đơn: giữ thông tin của đơn mới nhất
                previous = customers.get(key)
                if previous is None or line["createdAt"] > previous["_last_order_at"]:
                    customers[key] = {
                        "customer_key": key,
                        "customer_id": customer.get("id"),
                        "email": line.get("email"),
                        "phone": line.get("phone") or address.get("phone"),
                        "first_name": customer.get("firstName"),
                        "last_name": customer.get("lastName"),
                        "shipping_name": address.get("name"),
                        "address1": address.get("address1"),
                        "address2": address.get("address2"),
                        "city": address.get("city"),
                        "province": address.get("province"),
                        "zip": address.get("zip"),
                        "country": address.get("countryCodeV2"),
                        "_last_order_at": line["createdAt"],
                    }
        elif kind(line["id"]) == "LineItem":
            product = line.get("product") or {}
            items.append({
                "line_item_id": line["id"],
                "order_id": line["__parentId"],
                "sku": line.get("sku"),
                "name": line.get("name"),
                "title": line.get("title"),
                "variant_title": line.get("variantTitle"),
                "vendor": line.get("vendor"),
                "quantity": line.get("quantity"),
                "current_quantity": line.get("currentQuantity"),
                "original_unit_price": money(line.get("originalUnitPriceSet")),
                "original_total": money(line.get("originalTotalSet")),
                "discounted_total": money(line.get("discountedTotalSet")),
                "total_discount": money(line.get("totalDiscountSet")),
                # discounted_total chỉ trừ giảm giá gắn vào dòng, chưa trừ mã giảm giá cả giỏ và hàng trả lại
                # (mẫu 7/11: thổi doanh thu dòng lên ~6%). Hai trường dưới là giá sau MỌI giảm giá:
                "unit_price_after_discounts": money(line.get("discountedUnitPriceAfterAllDiscountsSet")),
                "line_net": money(line.get("priceAfterAllDiscountsBeforeTaxesSet")),  # sau trả hàng, chưa thuế
                "variant_id": (line.get("variant") or {}).get("id"),
                "product_id": product.get("id"),
                "product_type": product.get("productType"),
            })
    for row in customers.values():
        row["last_order_at"] = stamp(row.pop("_last_order_at"))
    return orders, items, refunds, customers


def split_products(lines: list[dict]) -> tuple[list, list]:
    products, variants = [], []
    for line in lines:
        if kind(line["id"]) == "Product":
            products.append({
                "product_id": line["id"],
                "title": line.get("title"),
                "handle": line.get("handle"),
                "product_type": line.get("productType"),
                "vendor": line.get("vendor"),
                "tags": ",".join(line.get("tags") or []),
                "status": line.get("status"),
                "created_at": stamp(line.get("createdAt")),
                "updated_at": stamp(line.get("updatedAt")),
            })
        elif kind(line["id"]) == "ProductVariant":
            variants.append({
                "variant_id": line["id"],
                "product_id": line["__parentId"],
                "sku": line.get("sku"),
                "title": line.get("title"),
                "price": Decimal(line["price"]) if line.get("price") else None,
                # Lựa chọn có TÊN, ví dụ [{"name": "Size", "value": "L"}, {"name": "...", "value": "MagSafe"}].
                # Dùng thay cho dò chữ trong title / tách SKU (SKU của shop có ít nhất 4 kiểu viết).
                "selected_options": [{"name": o.get("name"), "value": o.get("value")}
                                     for o in line.get("selectedOptions") or []],
                "created_at": stamp(line.get("createdAt")),
                "updated_at": stamp(line.get("updatedAt")),
            })
    return products, variants


HISTORY_FROM = "2024-11-01"
PHOENIX_OFFSET = "-07:00"  # ghi chỉ ngày thì Shopify hiểu mốc theo kiểu khác; luôn dùng mốc giờ đầy đủ
OVERLAP = timedelta(days=1)  # lấy lùi 1 ngày so với mốc để không sót đơn sửa sát giờ chạy


def fetch_orders(filter_: str) -> tuple[list, list, list, dict]:
    lines = bulk_lines(ORDERS_QUERY % {"filter": filter_})
    # Đơn tạo trước mốc lịch sử nhưng mới được sửa thì bỏ cả đơn, line item và thông tin khách của nó,
    # để raw luôn bắt đầu từ HISTORY_FROM. Lọc trên dòng thô trước khi tách bảng.
    start = datetime.fromisoformat(f"{HISTORY_FROM}T00:00:00{PHOENIX_OFFSET}")
    keep = {line["id"] for line in lines if kind(line["id"]) == "Order" and stamp(line["createdAt"]) >= start}
    lines = [line for line in lines if line["id"] in keep or line.get("__parentId") in keep]
    return split_orders(lines)


def clean(rows: list[dict]) -> list[dict]:
    """Bỏ cột nội bộ của dlt khi đọc lại từ BigQuery."""
    return [{k: v for k, v in row.items() if not k.startswith("_dlt")} for row in rows]


def merge(base: dict, delta: tuple) -> tuple[list, list, list, list]:
    """Gộp phần mới vào bản hiện có. base = {"orders", "items", "refunds", "customers"} (list dict)."""
    orders, items, refunds, customers = delta
    changed = {o["order_id"] for o in orders}
    merged_orders = {o["order_id"]: o for o in clean(base["orders"])}
    merged_orders.update({o["order_id"]: o for o in orders})
    merged_items = [i for i in clean(base["items"]) if i["order_id"] not in changed] + items
    merged_refunds = [r for r in clean(base["refunds"]) if r["order_id"] not in changed] + refunds
    merged_customers = {c["customer_key"]: c for c in clean(base["customers"])}
    for key, row in customers.items():
        old = merged_customers.get(key)
        if old is None or (row["last_order_at"] and (old.get("last_order_at") is None
                                                     or row["last_order_at"] >= old["last_order_at"])):
            merged_customers[key] = row
    return list(merged_orders.values()), merged_items, merged_refunds, list(merged_customers.values())


def watermark(base_orders: list[dict]) -> datetime | None:
    stamps = [o["updated_at"] for o in base_orders if o.get("updated_at")]
    return max(stamps) if stamps else None


@dlt.source(name="shopify", max_table_nesting=0)
def shopify(base: dict | None = None):
    """base: bản hiện có đọc từ BigQuery; None thì lấy full lịch sử."""
    mark = watermark(base["orders"]) if base else None
    if mark is None:
        filter_ = f"created_at:>='{HISTORY_FROM}T00:00:00{PHOENIX_OFFSET}'"
        print(f"== Shopify: bulk orders full từ {HISTORY_FROM} ==")
    else:
        since = (mark - OVERLAP).astimezone(timezone.utc)
        filter_ = f"updated_at:>='{since:%Y-%m-%dT%H:%M:%SZ}'"
        print(f"== Shopify: bulk orders sửa từ {since:%Y-%m-%d %H:%M} UTC (mốc {mark:%Y-%m-%d %H:%M} − 1 ngày) ==")
    delta = fetch_orders(filter_)
    print(f"  lấy về {len(delta[0]):,} đơn, {len(delta[1]):,} line item, {len(delta[2]):,} refund")
    if base and mark is not None:
        orders, items, refunds, customers = merge(base, delta)
        print(f"  sau khi gộp: {len(orders):,} đơn, {len(items):,} line item, {len(refunds):,} refund, "
              f"{len(customers):,} khách")
    else:
        orders, items, refunds, customers = delta[0], delta[1], delta[2], list(delta[3].values())
    print("== Shopify: bulk products ==")
    products, variants = split_products(bulk_lines(PRODUCTS_QUERY))
    print(f"  {len(products):,} sản phẩm, {len(variants):,} variant")

    tracker.save(mode="full" if mark is None else "incremental", filter=filter_)
    yield dlt.resource(orders, name="orders", primary_key="order_id")
    yield dlt.resource(items, name="order_line_items", primary_key="line_item_id")
    yield dlt.resource(refunds, name="order_refunds", primary_key="refund_id")
    yield dlt.resource(customers, name="pii_customers", primary_key="customer_key")
    yield dlt.resource(products, name="products", primary_key="product_id")
    yield dlt.resource(variants, name="product_variants", primary_key="variant_id",
                       columns={"selected_options": {"data_type": "json"}})
