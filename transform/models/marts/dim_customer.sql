-- Gold dim: 1 dòng = 1 khách (theo customer_key = sha256 email, không có PII).
-- Dựng từ fct_orders (đơn không test). Đơn không có email (customer_key null) không thuộc khách nào.
-- LTV = tổng rev (current_total, đã trừ hoàn) của mọi đơn của khách, tính tới lần nạp gần nhất.
select
    customer_key,
    min(order_date)                                  as first_order_date,
    max(order_date)                                  as last_order_date,
    format_date('%Y-%m', min(order_date))            as cohort_month,      -- tháng mua đầu tiên
    count(*)                                         as orders,
    countif(not is_cancelled)                        as orders_not_cancelled,
    count(*) > 1                                     as is_repeat,
    sum(rev)                                         as ltv,
    round(safe_divide(sum(rev), count(*)), 2)        as avg_order_value,
    sum(total_refunded)                              as total_refunded,
    date_diff(max(order_date), min(order_date), day) as days_first_to_last
from {{ ref('fct_orders') }}
where customer_key is not null
group by 1
