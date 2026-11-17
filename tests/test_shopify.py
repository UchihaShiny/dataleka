"""Kiểm nguồn Shopify bằng phản hồi giả: bulk operation, tách bảng, PII, tiền, chạy lại không trùng.
Không gọi Shopify, không dùng khoá GCP.

Chạy từ thư mục gốc:  python tests/test_shopify.py
"""

import json
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.stdout.reconfigure(encoding="utf-8")
import os  # noqa: E402
os.environ["DATAE_LOGS"] = tempfile.mkdtemp()  # không ghi vào sổ limit thật

from pipelines import common  # noqa: E402
from pipelines.sources import shopify as source  # noqa: E402
from test_common import FakeBigQuery  # noqa: E402


def order(n, email, cancelled=False, test=False):
    m = lambda v: {"shopMoney": {"amount": v}}  # noqa: E731
    return {
        "id": f"gid://shopify/Order/{n}", "name": f"#{1000 + n}", "email": email, "phone": None,
        "createdAt": f"2026-10-0{n}T08:00:00Z", "processedAt": f"2026-10-0{n}T08:00:00Z",
        "updatedAt": "2026-10-09T00:00:00Z", "cancelledAt": "2026-10-09T00:00:00Z" if cancelled else None,
        "cancelReason": None, "closedAt": None, "test": test, "displayFinancialStatus": "PAID",
        "displayFulfillmentStatus": "FULFILLED", "currencyCode": "USD", "sourceName": "web",
        "tags": ["a", "b"], "discountCodes": [],
        "subtotalPriceSet": m("40.00"), "currentSubtotalPriceSet": m("40.00"), "totalPriceSet": m("45.10"),
        "currentTotalPriceSet": m("45.10"), "totalDiscountsSet": m("0.00"), "currentTotalDiscountsSet": m("0.00"),
        "totalShippingPriceSet": m("5.10"), "totalTaxSet": m("0.00"), "currentTotalTaxSet": m("0.00"),
        "totalRefundedSet": m("10.00" if n == 1 else "0.00"),
        "customer": {"id": "gid://shopify/Customer/7", "firstName": "An", "lastName": "Nguyen"},
        "shippingAddress": {"name": "An Nguyen", "address1": "1 Main", "address2": None, "city": "Phoenix",
                            "province": "Arizona", "zip": "85001", "countryCodeV2": "US", "phone": "+1555"},
        "refunds": [{"id": "gid://shopify/Refund/1", "createdAt": "2026-10-05T00:00:00Z",
                     "totalRefundedSet": m("10.00")}] if n == 1 else [],
    }


def item(n, parent):
    m = lambda v: {"shopMoney": {"amount": v}}  # noqa: E731
    return {
        "id": f"gid://shopify/LineItem/{n}", "__parentId": parent, "sku": f"MHL{n}", "name": "Sun Hoodie",
        "title": "Sun Hoodie", "variantTitle": "M", "vendor": "DEERLY", "quantity": 1, "currentQuantity": 1,
        "originalUnitPriceSet": m("20.00"), "originalTotalSet": m("20.00"), "discountedTotalSet": m("20.00"),
        "totalDiscountSet": m("0.00"), "discountedUnitPriceAfterAllDiscountsSet": m("18.50"),
        "priceAfterAllDiscountsBeforeTaxesSet": m("18.50"), "variant": {"id": "gid://shopify/ProductVariant/5"},
        "product": {"id": "gid://shopify/Product/3", "productType": "Sun Hoodie"},
    }


ORDER_LINES = [
    order(1, " An@Example.com "), item(11, "gid://shopify/Order/1"), item(12, "gid://shopify/Order/1"),
    order(2, "an@example.com", cancelled=True), item(21, "gid://shopify/Order/2"),
    order(3, None, test=True), item(31, "gid://shopify/Order/3"),
]
PRODUCT_LINES = [
    {"id": "gid://shopify/Product/3", "title": "Sun Hoodie", "handle": "sun", "productType": "Sun Hoodie",
     "vendor": "DEERLY", "tags": ["deer"], "status": "ACTIVE", "createdAt": "2025-01-01T00:00:00Z",
     "updatedAt": "2026-01-01T00:00:00Z"},
    {"id": "gid://shopify/ProductVariant/5", "__parentId": "gid://shopify/Product/3", "sku": "MHL-M",
     "title": "M / Heavyweight Fleece Lining", "price": "39.99", "createdAt": "2025-01-01T00:00:00Z",
     "updatedAt": "2026-01-01T00:00:00Z",
     "selectedOptions": [{"name": "Size", "value": "M"}, {"name": "Material", "value": "Heavyweight Fleece Lining"}]},
]

calls, filters = [], []
DELTA_LINES = []  # phản hồi cho lần incremental


def fake_graphql(query, variables=None):
    calls.append(query)
    if "bulkOperationRunQuery" in query:
        assert "mutation" in query and "userErrors" in query
        which = "orders" if "orders(" in variables["q"] else "products"
        if which == "orders":
            filters.append(variables["q"].split('orders(query: "')[1].split('")')[0])
        return {"bulkOperationRunQuery": {"bulkOperation": {"id": which, "status": "CREATED"}, "userErrors": []}}
    which = variables["id"]
    polls = sum(1 for q in calls if "bulkOperation(id" in q)
    status = "RUNNING" if polls % 2 else "COMPLETED"  # lần đầu RUNNING, lần sau COMPLETED
    return {"bulkOperation": {"status": status, "errorCode": None, "objectCount": "7", "url": f"https://x/{which}"}}


class FakeDownload:
    def __init__(self, lines):
        self.text = "\n".join(json.dumps(line) for line in lines) + "\n"

    def raise_for_status(self):
        pass


def fake_get(url, timeout=None):
    if url.endswith("orders"):
        return FakeDownload(DELTA_LINES if filters and filters[-1].startswith("updated_at") else ORDER_LINES)
    return FakeDownload(PRODUCT_LINES)


with tempfile.TemporaryDirectory() as folder, patch.object(source, "graphql", fake_graphql), \
        patch.object(source.requests, "get", fake_get), patch.object(source.time, "sleep"):
    data_dir, bq = Path(folder), FakeBigQuery()
    for attempt in (1, 2):
        loaded = common.run(source.shopify(), "shopify", "shopify", bq=bq, data_dir=data_dir)
    assert filters == ["created_at:>='2024-11-01T00:00:00-07:00'"] * 2, filters
    assert loaded == {"orders": 3, "order_line_items": 4, "order_refunds": 1, "pii_customers": 1,
                      "products": 1, "product_variants": 1}, loaded

    tables = bq.tables
    assert tables["gia-lap.raw.shopify_orders"] == 3 and tables["gia-lap.raw.shopify_order_line_items"] == 4
    assert "gia-lap.pii.shopify_customers" in tables, "bảng PII phải vào dataset pii"
    assert not any(t.startswith("gia-lap.raw.") and "customer" in t for t in tables), tables

    items_schema = bq.schemas["gia-lap.raw.shopify_order_line_items"]
    assert items_schema["line_net"] == "NUMERIC" and items_schema["unit_price_after_discounts"] == "NUMERIC", \
        "giá dòng sau mọi giảm giá phải có và là tiền NUMERIC"
    assert "priceAfterAllDiscountsBeforeTaxesSet" in source.ORDERS_QUERY

    variants_schema = bq.schemas["gia-lap.raw.shopify_product_variants"]
    assert variants_schema["selected_options"] == "JSON", "lựa chọn biến thể (có tên) phải là cột JSON"
    assert "selectedOptions { name value }" in source.PRODUCTS_QUERY
    _, split = source.split_products(PRODUCT_LINES)
    assert split[0]["selected_options"] == [{"name": "Size", "value": "M"},
                                            {"name": "Material", "value": "Heavyweight Fleece Lining"}]
    assert source.split_products([{"id": "gid://shopify/ProductVariant/9", "__parentId": "p"}])[1][0][
        "selected_options"] == [], "biến thể không có lựa chọn thì danh sách rỗng, không lỗi"

    orders_schema = bq.schemas["gia-lap.raw.shopify_orders"]
    assert orders_schema["current_total"] == "NUMERIC" and orders_schema["created_at"] == "TIMESTAMP"
    for pii in ("email", "phone", "first_name", "last_name", "address1", "shipping_name"):
        assert pii not in orders_schema, f"raw.shopify_orders không được có cột {pii}"
    assert "customer_key" in orders_schema
    customers_schema = bq.schemas["gia-lap.pii.shopify_customers"]
    assert {"email", "customer_key", "address1"} <= set(customers_schema), customers_schema

    # Đọc lại file đã nạp để kiểm giá trị
    raw_orders = [json.loads(l) for p in sorted((data_dir / "shopify" / "raw" / "orders").glob("*.jsonl*"))
                  for l in common.gzip.open(p) if l.strip()]
    by_name = {o["order_name"]: o for o in raw_orders}
    assert by_name["#1001"]["customer_key"] == by_name["#1002"]["customer_key"], "cùng email phải cùng khoá"
    assert by_name["#1003"].get("customer_key") is None  # dlt bỏ giá trị null khỏi JSONL
    assert Decimal(str(by_name["#1001"]["current_total"])) == Decimal("45.10")
    assert by_name["#1002"]["cancelled_at"] and by_name["#1003"]["is_test"] is True

# Incremental: bản hiện có là kết quả lần full; đơn 1 được sửa (hoàn thêm tiền, line item đổi),
# đơn 4 mới, đơn 9 tạo trước 2024-11 mới được sửa (phải bỏ)
orders, items, refunds, customers = source.split_orders(ORDER_LINES)
base = {"orders": [{**o, "_dlt_id": "x"} for o in orders], "items": items, "refunds": refunds,
        "customers": list(customers.values())}
edited = order(1, "an@example.com")
edited.update({"updatedAt": "2026-11-09T05:00:00Z", "currentTotalPriceSet": {"shopMoney": {"amount": "30.10"}}})
new = order(4, "binh@example.com")
new["createdAt"] = new["processedAt"] = "2026-11-09T04:00:00Z"
old = order(9, "cu@example.com")
old["createdAt"] = "2024-05-01T00:00:00Z"
DELTA_LINES[:] = [edited, item(13, "gid://shopify/Order/1"), new, item(41, "gid://shopify/Order/4"),
                  old, item(91, "gid://shopify/Order/9")]
filters.clear()
with tempfile.TemporaryDirectory() as folder, patch.object(source, "graphql", fake_graphql),         patch.object(source.requests, "get", fake_get), patch.object(source.time, "sleep"):
    bq = FakeBigQuery()
    loaded = common.run(source.shopify(base), "shopify", "shopify", bq=bq, data_dir=Path(folder))
    # Mốc = updated_at lớn nhất (2026-10-09) trừ 1 ngày
    assert filters == ["updated_at:>='2026-10-08T00:00:00Z'"], filters
    assert loaded["orders"] == 4, loaded  # 3 cũ + 1 mới, đơn 9 bị bỏ
    assert loaded["order_line_items"] == 4, loaded  # đơn 1: 2 dòng cũ thay bằng 1 dòng mới; +1 của đơn 4
    assert loaded["pii_customers"] == 2, loaded
merged = source.merge(base, source.split_orders(DELTA_LINES[:4]))  # đơn sửa + đơn mới
by_id = {o["order_id"]: o for o in merged[0]}
assert by_id["gid://shopify/Order/1"]["current_total"] == Decimal("30.10"), "đơn sửa phải lấy bản mới"
assert not any("_dlt_id" in o for o in merged[0]), "bỏ cột nội bộ dlt của bản cũ"
assert sorted(i["line_item_id"] for i in merged[1] if i["order_id"] == "gid://shopify/Order/1") == [
    "gid://shopify/LineItem/13"], "line item của đơn sửa phải được thay, không cộng dồn"

# Hàm khoá: chuẩn hoá hoa thường và khoảng trắng
assert source.customer_key(" A@B.com") == source.customer_key("a@b.com")
print("PASS: bulk orders/products, tách line item, refund, PII sang dataset pii, tiền NUMERIC, chạy lại không trùng, "
      "incremental theo updated_at gộp đúng")
