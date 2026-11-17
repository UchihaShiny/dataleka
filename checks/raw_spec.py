"""Danh sách bảng raw cần có, dùng cho check_raw.py."""

from datetime import date

# bảng: (khoá chính, cột ngày, lịch sử phải bắt đầu từ ngày này hoặc sớm hơn)
EXPECTED = {
    "Shopify": {
        "raw.shopify_orders": ("order_id", "created_at", date(2024, 11, 1)),
        "raw.shopify_order_line_items": ("line_item_id", None, None),
        "raw.shopify_order_refunds": ("refund_id", "created_at", None),
        "raw.shopify_products": ("product_id", None, None),
        "raw.shopify_product_variants": ("variant_id", None, None),
        "pii.shopify_customers": ("customer_key", None, None),
    },
    "Meta": {
        # Meta nạp dần mỗi tiếng một tháng (2026-11-09), chưa đặt mốc lịch sử bắt buộc
        "raw.meta_ad_insights_daily": ("ad_account_id, date, ad_id", "date", None),
        "raw.meta_ads": ("ad_id", None, None),
    },
    "Klaviyo": {
        "raw.klaviyo_campaigns": ("campaign_id", None, None),
        "raw.klaviyo_flows": ("flow_id", None, None),
        "raw.klaviyo_campaign_messages": ("message_id", None, None),
        "raw.klaviyo_flow_messages": ("message_id", None, None),
        "raw.klaviyo_metrics": ("metric_id", None, None),
        "raw.klaviyo_message_daily": ("date, metric, message_id", "date", None),
    },
}
# Bảng đại diện để đo độ mới của từng nguồn: (bảng, cột thời gian)
FRESHNESS = {
    "Shopify": ("raw.shopify_orders", "max(created_at)"),
    "Meta": ("raw.meta_ad_insights_daily", "max(date)"),
    "Klaviyo": ("raw.klaviyo_message_daily", "max(date)"),
}
