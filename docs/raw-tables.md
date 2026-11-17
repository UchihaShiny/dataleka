# Từ điển tầng raw (Bronze)

Project `datae-514203`, BigQuery Sandbox, location US. Số dòng tính đến ngày 2026-11-09.

**Cách nạp chung:** dlt ghi JSONL tạm trên máy, rồi một load job ghi đè cả bảng (`WRITE_TRUNCATE`). Kiểu cột lấy từ schema của dlt, không để BigQuery tự đoán. Sandbox không có DML, nên không dùng MERGE. Chạy lại bao nhiêu lần cũng không tạo dòng trùng.

**Lệnh nạp:**
- Cả hệ (raw → dbt build → dự báo): `python -m pipelines.run`; chỉ tầng raw: `python -m pipelines.run --skip dbt forecast`
- Kiểm tra: `python checks/check_raw.py` (đủ bảng, khoá trùng, độ mới 36 giờ, dung lượng) và `python checks/reconcile.py` (so với số đếm do nguồn trả).

## Shopify (Admin GraphQL, bulk operation)

Lần đầu lấy full đơn từ 2024-11-01. Các lần sau chỉ kéo đơn có `updated_at` từ mốc mới nhất trừ 1 ngày, rồi gộp vào bản hiện có theo `order_id`. Products và variants lấy full mỗi lần.

| Bảng | Khoá | Dòng | Cột chính |
|---|---|---|---|
| `raw.shopify_orders` | `order_id` | 11.014 | `order_name`, `created_at`, `updated_at`, `cancelled_at`, `is_test`, `financial_status`, `current_total`, `total_price`, `total_refunded`, `total_discounts`, `total_shipping`, `total_tax`, `customer_key`, `source_name`, `tags`, `shipping_country` |
| `raw.shopify_order_line_items` | `line_item_id` | 16.972 | `order_id`, `sku`, `product_id`, `variant_id`, `product_type`, `quantity`, `current_quantity`, `original_unit_price`, `discounted_total` |
| `raw.shopify_order_refunds` | `refund_id` | 114 | `order_id`, `created_at`, `total_refunded` |
| `raw.shopify_products` | `product_id` | 4.696 | `title`, `product_type`, `tags`, `status`, `vendor` |
| `raw.shopify_product_variants` | `variant_id` | 100.379 | `product_id`, `sku`, `title`, `price` |
| `pii.shopify_customers` | `customer_key` | 9.077 | `email`, `first_name`, `last_name`, `phone`, `address1`, `city`, `province`, `zip`, `country`, `last_order_at` |

**Bẫy:**
- `created_at` là giờ **UTC**. Silver phải đổi sang America/Phoenix trước khi lấy ngày.
- **Rev = `current_total`** (đã trừ refund và chỉnh sửa đơn), theo brief.
- `customer_key` = sha256 của email đã viết thường và bỏ khoảng trắng. Đơn không có email thì để null.
- PII chỉ nằm ở `pii.shopify_customers`. Thông tin lấy theo đơn mới nhất của khách. File tạm có PII trên máy bị xoá sau mỗi lần nạp.
- Shop tạo sản phẩm mới liên tục (97 sản phẩm chỉ trong 2 giờ ngày 9/11), nên số dòng products thay đổi giữa các lần nạp là bình thường.
- Product type đọc từ `product_type` và tiền tố SKU: MHL = Sun Hoodie, SSS = Button-up, AUX = Short Sleeve tee, RGO = Ornament. Việc này làm ở silver.

## Meta Ads (Marketing API Insights, chỉ đọc)

Gọi theo từng tháng. Số đã lấy được lưu cache theo ngày ở `data/meta_cache/`, nên mỗi lần chỉ gọi Meta cho khoảng ngày yêu cầu. Chỉ gọi những tài khoản có spend. Cây ad lưu cache 24 giờ. Có bộ giữ quota: giãn 15 giây giữa 2 lần gọi, mức dùng từ 50% thì chờ, từ 75% thì dừng, không chạy trong giờ làm việc Phoenix.

| Bảng | Khoá | Dòng | Cột chính |
|---|---|---|---|
| `raw.meta_ad_insights_daily` | `ad_account_id, date, ad_id` | 7.489 (1/10 – 8/11) | `campaign_id/name`, `adset_id/name`, `ad_name`, `spend`, `impressions`, `reach`, `clicks`, `inline_link_clicks`, `actions` (JSON), `action_values` (JSON) |
| `raw.meta_ads` | `ad_id` | 2.546 | `created_time`, `effective_status`, `campaign_objective`, `creative_id` |

**Bẫy:**
- `date` là ngày theo múi giờ tài khoản (GMT−7, trùng với Phoenix).
- **Purchase của Meta bị thổi khoảng 1,6×.** MER và CPO tính bằng đơn Shopify, ROAS Meta chỉ để tham khảo.
- Trong `actions` có nhiều mục trùng nghĩa (`purchase`, `omni_purchase`...). Silver chỉ lấy `purchase`, không cộng dồn.
- `reach` là số theo ngày, cộng các ngày lại không ra số người duy nhất.
- Tổng spend cấp ad có thể thấp hơn spend cấp tài khoản vài chục xu mỗi ngày, và điều này có ngay ở phía Meta (ví dụ 8/10 thiếu 0,34, 23/10 thiếu 0,53). Spend cho cả tài khoản nên lấy theo tài khoản nếu cần chính xác tới xu. `reconcile.py` cho phép chênh tối đa 1 USD mỗi ngày.
- Mấy ngày gần nhất Meta còn chỉnh nhẹ (ví dụ lệch 0,23 ở ngày 1/11). Vì vậy lần chạy hằng ngày lấy lại 7 ngày.
- `meta_ads` chỉ có tài khoản đã từng có spend trong các khoảng đã nạp.

## Klaviyo (REST API, private key read-only)

Không lấy từng event thô. Dùng Query Metric Aggregates để đếm theo ngày Phoenix × message, nên không có PII. Cache theo ngày ở `data/klaviyo_cache/`.

| Bảng | Khoá | Dòng | Cột chính |
|---|---|---|---|
| `raw.klaviyo_campaigns` | `campaign_id` | 53 | `name`, `builder`, `archived`, `send_strategy` |
| `raw.klaviyo_campaign_messages` | `message_id` | 53 | `campaign_id`, `name`, `status`, `send_time` |
| `raw.klaviyo_flows` | `flow_id` | 11 | `name`, `status`, `trigger_type` |
| `raw.klaviyo_flow_messages` | `message_id` | 38 | `flow_id`, `action_ids` (một message có thể nằm dưới nhiều bước khi A/B test), `name`, `channel` |
| `raw.klaviyo_metrics` | `metric_id` | 72 | `name`, `integration` |
| `raw.klaviyo_message_daily` | `date, metric, message_id` | 2.545 (1/10 – 7/11) | `metric` (received, opened, clicked, placed_order), `count`, `value` (doanh thu, chỉ có ở placed_order) |

**Bẫy:**
- received, opened, clicked nhóm theo `$message`; placed_order nhóm theo `$attributed_message`.
- `message_id = '(none)'` là đơn mà Klaviyo không gán cho email nào. Tính doanh thu email thì phải bỏ những dòng này.
- `message_id` nối về `klaviyo_campaign_messages` (campaign) hoặc `klaviyo_flow_messages` (flow).
- Flow messages lấy lại mỗi 24 giờ (cache `data/klaviyo_cache/flow_messages.json`), vì đi hết các flow tốn khoảng 90 lần gọi.
- `value` Klaviyo trả về dạng số thực, được làm tròn về 2 chữ số.
- Revision API mới đã dời các trường vào `attributes.definition` và bỏ bộ lọc `messages.channel`.

## Chung cho cả 3 nguồn

- Cột nào mà mọi dòng đều null thì dlt không tạo cột đó, ví dụ `cancel_reason` khi chưa có đơn huỷ. Silver phải chịu được trường hợp thiếu cột.
- Mỗi bảng có thêm `_dlt_load_id` và `_dlt_id` của dlt, có thể bỏ qua.
- Sandbox tự xoá bảng sau 60 ngày. Chạy lại `python -m pipelines.run` là có lại.
