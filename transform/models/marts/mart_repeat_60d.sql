-- Gold (tuần 4, câu mẫu 3): 1 dòng = 1 khách có ít nhất 1 đơn KHÔNG HUỶ. Khách có mua lần 2 trong 60 ngày không,
-- xếp theo product type (product_line) của đơn đầu. Huy Anh chốt 13/11:
--   - bỏ đơn huỷ ở cả đơn đầu và đơn 2 (như mart_rfm): khách huỷ rồi đặt lại không bị tính là mua lần 2;
--   - đơn đầu nhiều type → type có doanh thu dòng lớn nhất (hoà thì theo tên), cờ is_multi_type để biết;
--   - mua lần 2 = có đơn không huỷ vào NGÀY KHÁC, 1–60 ngày sau ngày đơn đầu (ngày Phoenix). Đơn thêm cùng ngày
--     (quên món, đặt bù) coi là cùng lần mua, ghi riêng ở has_same_day_extra.
-- is_eligible: chỉ khách có đơn đầu từ 60 ngày trước ngày đã trọn cuối mới tính tỉ lệ (khách mới chưa đủ 60 ngày để
-- quay lại, đưa vào mẫu số sẽ kéo tỉ lệ xuống). Ngày đã trọn cuối = macro complete_through (theo lúc nạp Shopify).
-- Bẫy: kho Shopify chỉ có từ 11/2024, khách đơn đầu 11/2024 có thể đã mua trước đó (như cohort 2024-11).
-- Khác dim_customer (đếm cả đơn huỷ), nên số khách ở đây ít hơn một chút.
with as_of as (
    select {{ complete_through() }} as as_of_date   -- ngày đã trọn (macro complete_through, 16/11)
),
orders as (
    select customer_key, order_id, order_date, created_at,
           row_number() over (partition by customer_key order by created_at, order_id) as rn
    from {{ ref('fct_orders') }}
    where customer_key is not null and not is_cancelled
),
first_order as (
    select customer_key, order_id as first_order_id, order_date as first_order_date
    from orders where rn = 1
),
first_lines as (
    -- doanh thu theo type trong đơn đầu, bỏ dòng không phải sản phẩm (Tip, Shipping Protection, Gift Card)
    select f.customer_key, l.product_line, sum(l.line_revenue) as rev
    from first_order f
    join {{ ref('fct_lines') }} l on l.order_id = f.first_order_id
    where not {{ is_non_product('l.product_title') }}
    group by 1, 2
),
first_type as (
    select customer_key,
           array_agg(product_line order by rev desc, product_line limit 1)[offset(0)] as first_type,
           count(*)                                                                as n_types_first_order
    from first_lines
    group by 1
),
later as (
    select f.customer_key,
           min(if(o.order_date > f.first_order_date, o.order_date, null))         as second_order_date,
           countif(o.rn > 1 and o.order_date = f.first_order_date) > 0            as has_same_day_extra
    from first_order f
    join orders o using (customer_key)
    group by 1
)
select
    f.customer_key,
    f.first_order_id,
    f.first_order_date,
    format_date('%Y-%m', f.first_order_date)                                       as cohort_month,
    coalesce(t.first_type, '(không rõ)')                                           as first_type,
    coalesce(t.n_types_first_order, 0)                                             as n_types_first_order,
    coalesce(t.n_types_first_order, 0) > 1                                         as is_multi_type,
    l.has_same_day_extra,
    l.second_order_date,
    date_diff(l.second_order_date, f.first_order_date, day)                        as days_to_second,
    a.as_of_date,
    f.first_order_date <= date_sub(a.as_of_date, interval 60 day)                  as is_eligible,
    if(f.first_order_date <= date_sub(a.as_of_date, interval 60 day),
       coalesce(date_diff(l.second_order_date, f.first_order_date, day) <= 60, false),
       null)                                                                       as repeat_60d
from first_order f
cross join as_of a
left join first_type t using (customer_key)
left join later l using (customer_key)
