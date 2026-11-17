-- Silver: 1 dòng = 1 lần hoàn tiền của 1 đơn (1 đơn có thể hoàn nhiều lần).
-- refund_date là ngày HOÀN (giờ Phoenix), thường sau ngày đặt đơn vài ngày đến vài tuần.
-- Hai cách nhìn hoàn tiền, đều đúng, dùng cho câu hỏi khác nhau:
--   - theo ngày đặt: rev = current_total của đơn đã trừ sẵn tiền hoàn (Rev ngày cũ giảm dần khi có hoàn)
--   - theo ngày hoàn: bảng này, để biết mỗi ngày shop phải trả lại bao nhiêu tiền
select
    refund_id,
    order_id,
    created_at,                                          -- giờ UTC
    date(created_at, 'America/Phoenix')   as refund_date,
    cast(total_refunded as numeric)       as refund_amount
from {{ source('raw', 'shopify_order_refunds') }}
