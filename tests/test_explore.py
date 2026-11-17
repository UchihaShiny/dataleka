"""Kiểm bộ khám phá schema bằng phản hồi giả: profile JSON lồng nhau, Meta tự bỏ trường bị từ chối,
Shopify dựng câu truy vấn từ introspection mà không lấy PII, Klaviyo lưu đủ bảng. Không gọi mạng.

Chạy từ thư mục gốc:  python tests/test_explore.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "checks"))
sys.stdout.reconfigure(encoding="utf-8")
os.environ["DATAE_LOGS"] = tempfile.mkdtemp()
os.environ.setdefault("META_ACCESS_TOKEN", "gia")
os.environ.setdefault("META_API_VERSION", "v27.0")

import explore_klaviyo  # noqa: E402
import explore_meta  # noqa: E402
import explore_shopify  # noqa: E402
import profile_sample  # noqa: E402
from pipelines.sources import meta  # noqa: E402

TMP = Path(tempfile.mkdtemp())
profile_sample.EXPLORE = TMP / "explore"


def load(source, name):
    return json.loads((profile_sample.EXPLORE / source / f"{name}.json").read_text(encoding="utf-8"))


# 1. Profile: duỗi JSON lồng nhau, đếm tỉ lệ có giá trị, ẩn ví dụ của trường PII
records = [
    {"id": "1", "spec": {"link": {"cta": {"type": "SHOP_NOW"}}}, "actions": [{"action_type": "purchase", "value": "2"}],
     "email": "a@b.c", "empty": None},
    {"id": "2", "spec": {"link": {"cta": {"type": "LEARN_MORE"}}}, "actions": [], "email": None, "empty": ""},
]
rows = {r["path"]: r for r in profile_sample.profile(records)}
assert rows["spec.link.cta.type"]["filled"] == 2 and rows["spec.link.cta.type"]["distinct"] == 2, rows
assert rows["actions[].action_type"]["filled"] == 1 and rows["actions[].value"]["kinds"] == "số dạng chuỗi", rows
assert rows["email"]["example"] == "(ẩn)", "không in ví dụ của trường PII"
assert rows["empty"]["filled"] == 0
profile_sample.save("demo", "bang", records)
profile_sample.save("demo", "_schema_x", {"fields": []})
text = Path(profile_sample.report("demo")).read_text(encoding="utf-8")
assert "## bang (2 bản ghi" in text and "_schema_x" not in text and "a@b.c" not in text, text

# 2. Meta: đọc tên trường bị từ chối trong câu báo lỗi, không bao giờ bỏ id
assert explore_meta.bad_field("(#100) Tried accessing nonexisting field (foo_bar) on node type (Campaign)",
                              ["id", "name", "foo_bar"]) == "foo_bar"
assert explore_meta.bad_field("(#100) Param fields: field learning_stage_info requires permission",
                              ["id", "learning_stage_info", "name"]) == "learning_stage_info"
assert explore_meta.bad_field("(#100) Unsupported get request", ["id", "name"]) is None
assert explore_meta.bad_field("(#100) Tried accessing nonexisting field (id)", ["id"]) is None

# 3. Meta chạy đủ: metadata, bỏ trường bị từ chối, lọc theo id, insights rộng + theo vị trí
cache = TMP / "meta_cache"
(cache / "insights").mkdir(parents=True)
(cache / "insights" / "2026-11-07.json").write_text(json.dumps([
    {"ad_account_id": "111", "campaign_id": "c1", "adset_id": "s1", "ad_id": f"a{i}", "spend": "5"} for i in range(3)
]), encoding="utf-8")
(cache / "ads.json").write_text(json.dumps({"111": {"fetched_at": 0, "ads": [
    {"ad_id": f"a{i}", "creative_id": f"cr{i % 2}"} for i in range(3)]}}), encoding="utf-8")
calls = []


def fake_get(path, params):
    calls.append((path, dict(params)))
    if params.get("metadata"):
        kind = {"c1": "campaign", "s1": "adset", "a0": "ad", "cr0": "adcreative"}[path]
        if kind == "adcreative":
            return {"id": path}  # creative không trả metadata → dùng bộ trường dự phòng
        return {"id": path, "metadata": {"fields": [{"name": "id"}, {"name": "name"}, {"name": "bi_chan"}],
                                         "connections": {"ads": "url"}}}
    if "bi_chan" in params.get("fields", ""):
        raise meta.MetaError("x", {"code": 100, "message": "(#100) Tried accessing nonexisting field (bi_chan)"})
    return {"id": path, "name": "n"}


def fake_get_all(path, params):
    calls.append((path, dict(params)))
    if "bi_chan" in params.get("fields", ""):
        raise meta.MetaError("x", {"code": 100, "message": "(#100) Tried accessing nonexisting field (bi_chan)"})
    if path.endswith("/insights"):
        if params.get("breakdowns"):
            return [{"campaign_id": "c1", "publisher_platform": "facebook", "spend": "15"}]
        return [{"ad_id": "a0", "spend": "5", "purchase_roas": [{"action_type": "omni_purchase", "value": "3.1"}]}]
    if path.endswith("/adcreatives"):
        raise meta.MetaError("x", {"code": 100, "message": "(#100) Filtering field id is not supported"})
    ids = json.loads(params["filtering"])[0]["value"]
    return [{"id": i, "name": "n"} for i in ids if i != "a2"]  # a2 giả làm ad đã xoá


with patch.object(explore_meta, "CACHE", cache), patch.object(meta, "get", fake_get), \
        patch.object(meta, "get_all", fake_get_all), patch.object(meta.tracker, "save", lambda **k: None), \
        patch.object(sys, "argv", ["explore_meta.py", "--force"]):
    explore_meta.main()
assert [r["id"] for r in load("meta", "campaign")] == ["c1"]
assert [r["id"] for r in load("meta", "ad")] == ["a0", "a1"], "ad đã xoá thì không có, script chỉ báo"
assert {r["id"] for r in load("meta", "adcreative")} == {"cr0", "cr1"}, "lọc id bị từ chối thì lấy lẻ từng node"
assert load("meta", "insights_rong")[0]["purchase_roas"][0]["value"] == "3.1"
assert load("meta", "insights_theo_vi_tri")[0]["publisher_platform"] == "facebook"
assert len(load("meta", "insights_hien_tai")) == 3
dropped = load("meta", "_dropped")
assert {d["field"] for d in dropped} == {"bi_chan"} and all(d["field"] != "id" for d in dropped), dropped
creative_fields = next(p["fields"] for path, p in calls if path == "cr0" and "metadata" not in p)
assert "object_story_spec" in creative_fields, "creative không có metadata thì dùng bộ trường dự phòng"
assert not any("ids" in p for _, p in calls), "v26+ đã bỏ ?ids="

# 4. Shopify: chọn trường từ introspection, bỏ PII và trường cần tham số, tiền lấy shopMoney
NN = {"kind": "NON_NULL", "name": None}
described = {"fields": [
    {"name": "id", "args": [], "type": {**NN, "ofType": {"kind": "SCALAR", "name": "ID"}}},
    {"name": "displayFinancialStatus", "args": [], "type": {"kind": "ENUM", "name": "S"}},
    {"name": "tags", "args": [], "type": {**NN, "ofType": {"kind": "LIST", "name": None,
                                                         "ofType": {"kind": "SCALAR", "name": "String"}}}},
    {"name": "currentTotalPriceSet", "args": [], "type": {**NN, "ofType": {"kind": "OBJECT", "name": "MoneyBag"}}},
    {"name": "email", "args": [], "type": {"kind": "SCALAR", "name": "String"}},
    {"name": "phone", "args": [], "type": {"kind": "SCALAR", "name": "String"}},
    {"name": "note", "args": [], "type": {"kind": "SCALAR", "name": "String"}},
    {"name": "clientIp", "args": [], "type": {"kind": "SCALAR", "name": "String"}},
    {"name": "shippingAddress", "args": [], "type": {"kind": "OBJECT", "name": "MailingAddress"}},
    {"name": "metafield", "args": [{"name": "key", "type": {"kind": "NON_NULL"}}],
     "type": {"kind": "SCALAR", "name": "String"}},
    {"name": "app", "args": [], "type": {"kind": "OBJECT", "name": "App"}},
]}
picked = explore_shopify.selection(described)
assert picked == ["id", "displayFinancialStatus", "tags",
                  "currentTotalPriceSet { shopMoney { amount currencyCode } }"], picked
assert explore_shopify.window(__import__("datetime").date(2026, 11, 7)) == (
    "'2026-11-07T00:00:00-07:00'", "'2026-11-08T00:00:00-07:00'")

# 5. Shopify chạy đủ: trường bị chặn (ACCESS_DENIED) bị bỏ đúng kiểu, tách line item/refund, không có PII
queries = []
fake_types = {"Order": described, "LineItem": {"fields": described["fields"][:2]},
              "Refund": {"fields": described["fields"][:1]}, "Product": {"fields": described["fields"][:1]},
              "ProductVariant": {"fields": described["fields"][:1]}, "Customer": {"fields": described["fields"][4:6]}}


def fake_graphql(query, variables=None):
    return {"__type": fake_types[variables["name"]]}


def fake_body(query):
    queries.append(query)
    if "orders(" in query:
        assert "created_at:>='2026-11-07T00:00:00-07:00' AND created_at:<'2026-11-08T00:00:00-07:00'" in query
        if "tags" in query.split("refunds")[0]:
            return {"errors": [{"message": "Access denied for tags field.", "path": ["orders", "nodes", 0, "tags"]}],
                    "data": None}
        return {"data": {"orders": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [{
            "id": "gid://shopify/Order/1", "displayFinancialStatus": "PAID",
            "refunds": [{"id": "gid://shopify/Refund/9"}],
            "lineItems": {"nodes": [{"id": "gid://shopify/LineItem/5", "displayFinancialStatus": None,
                                     "variant": {"id": "v"}, "product": {"id": "p"}}]}}]}}}
    root = "productVariants" if "productVariants(" in query else "products"
    return {"data": {root: {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [{"id": "gid://x/1"}]}}}


with patch.object(explore_shopify.shopify, "graphql", fake_graphql), \
        patch.object(explore_shopify.shopify, "graphql_body", fake_body), \
        patch.object(explore_shopify.shopify.tracker, "save", lambda **k: None), \
        patch.object(sys, "argv", ["explore_shopify.py"]):
    explore_shopify.main()
assert not any(word in q for q in queries for word in ("email", "phone", "note", "clientIp", "shippingAddress"))
assert load("shopify", "line_items")[0]["order_id"] == "gid://shopify/Order/1"
assert load("shopify", "refunds")[0]["order_id"] == "gid://shopify/Order/1"
assert "lineItems" not in load("shopify", "orders")[0]
assert load("shopify", "_dropped") == [{"where": "orders.Order", "field": "tags",
                                        "reason": "Access denied for tags field."}]
order_queries = [q for q in queries if "orders(" in q]
assert len(order_queries) == 2 and "tags" not in order_queries[-1].split("refunds")[0], "bỏ tags rồi gọi lại 1 lần"
assert "_schema_Customer.json" in {p.name for p in (profile_sample.EXPLORE / "shopify").iterdir()}

# 6. Klaviyo: lưu nguyên JSON:API, chỉ đi 3 flow đầu, Placed Order nhóm theo message và flow
paths = []


def fake_k_get_all(path, params=None):
    paths.append(path)
    if path == "/campaigns":
        return ([{"id": "cp1", "type": "campaign", "attributes": {"definition": {"name": "Sale"}}}],
                [{"id": "m1", "type": "campaign-message", "attributes": {}}, {"id": "t", "type": "tag"}])
    if path == "/flows":
        return [{"id": f"f{i}", "type": "flow", "attributes": {"name": f"Flow {i}"}} for i in range(5)], []
    if path.endswith("/flow-actions"):
        return [{"id": f"act-{path.split('/')[2]}", "type": "flow-action"}], []
    if path.endswith("/flow-messages"):
        return [{"id": "fm", "type": "flow-message"}], []
    if path == "/metrics":
        return [{"id": "PO", "attributes": {"name": "Placed Order"}}, {"id": "OE", "attributes": {"name": "x"}}], []
    raise AssertionError(path)


aggregates = []
with patch.object(explore_klaviyo.klaviyo, "get_all", fake_k_get_all), \
        patch.object(explore_klaviyo.klaviyo, "aggregate",
                     lambda m, by, s, e, with_value: aggregates.append((m, by, s, e)) or (["2026-11-07"], [
                         {"dimensions": ["msg"], "measurements": {"count": [3], "sum_value": [120.5]}}])), \
        patch.object(explore_klaviyo.klaviyo.tracker, "save", lambda **k: None), \
        patch.object(sys, "argv", ["explore_klaviyo.py"]):
    explore_klaviyo.main()
assert [m["id"] for m in load("klaviyo", "campaign_messages")] == ["m1"]
assert sum(1 for p in paths if p.endswith("/flow-actions")) == 3
assert {a[1] for a in aggregates} == {"$attributed_message", "$attributed_flow"}
assert all(a[0] == "PO" and str(a[2]) == str(a[3]) == "2026-11-07" for a in aggregates)
assert load("klaviyo", "placed_order_theo_attributed_message")[0]["measurements"]["sum_value"] == [120.5]
assert not any("events" in p for p in paths), "không lấy event thô (có email)"

print("PASS: profile JSON lồng nhau + ẩn PII, Meta metadata + bỏ trường bị từ chối + lấy lẻ khi không lọc được, "
      "Shopify dựng truy vấn từ introspection không PII + bỏ trường bị chặn, Klaviyo lưu đủ bảng")
