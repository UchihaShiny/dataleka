-- Silver: 1 dòng = 1 đơn Shopify, đã đổi sang ngày kinh doanh theo giờ Phoenix.
-- Chỉ đổi kiểu, đổi tên, thêm cờ. Chưa lọc đơn nào: quyết định tính đơn nào là việc của gold.
select
    order_id,
    order_name,
    created_at,                                              -- giờ UTC, giữ nguyên để đối chiếu
    date(created_at, 'America/Phoenix')       as order_date, -- ngày kinh doanh (brief: ngày theo Phoenix)
    updated_at,
    cancelled_at,
    cancelled_at is not null                  as is_cancelled,
    coalesce(is_test, false)                  as is_test,
    financial_status,
    source_name,
    shipping_country,
    customer_key,                                            -- sha256 của email, không phải PII
    cast(current_total as numeric)            as rev,        -- brief: Rev = current_total (đã trừ hoàn, sửa đơn)
    cast(total_price as numeric)              as total_price,
    cast(total_refunded as numeric)           as total_refunded,
    cast(total_discounts as numeric)          as total_discounts,
    cast(total_shipping as numeric)           as total_shipping,
    cast(total_tax as numeric)                as total_tax
from {{ source('raw', 'shopify_orders') }}
