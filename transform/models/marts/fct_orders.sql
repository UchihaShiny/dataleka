-- Gold fact: 1 dòng = 1 đơn Shopify (không tính đơn test). Mức chi tiết nhất của đơn hàng.
-- Mọi bảng tổng (daily_performance, dim_customer) dựng từ đây, nên định nghĩa "đơn nào được tính" chỉ ở 1 chỗ.
with orders as (
    select * from {{ ref('stg_orders') }}
    where not is_test
),

lines as (
    select
        order_id,
        count(*)                   as line_count,
        sum(quantity)              as units,
        sum(current_quantity)      as current_units
    from {{ ref('stg_line_items') }}
    group by 1
)

select
    o.order_id,
    o.order_name,
    o.order_date,                                    -- ngày đặt theo Phoenix
    o.created_at,
    o.customer_key,                                  -- sha256 email, nối dim_customer; null = đơn không email
    case
        when o.customer_key is null then null
        else row_number() over (partition by o.customer_key order by o.created_at, o.order_id) = 1
    end                                              as is_first_order,
    o.is_cancelled,
    o.financial_status,
    o.source_name,
    o.shipping_country,
    o.rev,                                           -- current_total: sau hoàn và sửa đơn
    o.total_price,                                   -- lúc đặt, trước hoàn
    o.total_discounts,
    o.total_shipping,
    o.total_tax,
    o.total_refunded,
    coalesce(r.refund_count, 0)                      as refund_count,
    r.first_refund_date,
    coalesce(l.line_count, 0)                        as line_count,
    coalesce(l.units, 0)                             as units,
    coalesce(l.current_units, 0)                     as current_units
from orders o
left join {{ ref('int_order_refunds') }} r on r.order_id = o.order_id
left join lines l on l.order_id = o.order_id
