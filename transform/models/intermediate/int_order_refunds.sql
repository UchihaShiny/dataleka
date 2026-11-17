-- Intermediate: 1 dòng = 1 đơn có hoàn tiền. Gom các lần hoàn của 1 đơn (1 đơn có thể hoàn nhiều lần).
-- Dùng cho fct_orders (đơn này hoàn mấy lần, lần đầu khi nào).
select
    order_id,
    count(*)                     as refund_count,
    sum(refund_amount)           as refund_amount,
    min(refund_date)             as first_refund_date,
    max(refund_date)             as last_refund_date
from {{ ref('stg_refunds') }}
group by 1
