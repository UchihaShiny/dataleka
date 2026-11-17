-- Silver: 1 dòng = 1 ngày (Phoenix) × 1 message × 1 metric (received, opened, clicked, placed_order).
-- Brief ghi stg_klaviyo_events: DataE cố ý KHÔNG lấy event thô (có email người nhận), chỉ lấy số đếm
-- ngày × message qua Query Metric Aggregates, nên model này thay cho stg_klaviyo_events.
-- message_id = '(none)': đơn Placed Order không gán cho email nào (đa số đơn). Giữ lại để tổng khớp Shopify,
-- nhưng is_attributed = false để không tính vào doanh thu email.
select
    date,
    message_id,
    metric,
    message_id != '(none)'                 as is_attributed,
    count,
    cast(value as numeric)                 as value          -- doanh thu, chỉ có ở placed_order
from {{ source('raw', 'klaviyo_message_daily') }}
