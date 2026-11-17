-- Gold (mô hình 1, Cohort Analysis): 1 dòng = 1 cohort (tháng mua đơn đầu) × 1 tháng thứ k kể từ tháng đầu.
-- Đây là "bảng tam giác giữ khách": hàng = cohort, cột = tháng thứ 0, 1, 2... , ô = % khách của cohort còn mua ở tháng đó.
--
--   cohort_month     = tháng mua đơn đầu của khách (giờ Phoenix), LẤY TỪ dim_customer để cùng một định nghĩa
--   month_offset     = k: tháng của đơn − tháng cohort (0 = chính tháng mua đầu)
--   cohort_size      = số khách của cohort
--   active_customers = số khách của cohort có ít nhất 1 đơn trong tháng thứ k
--   retention_pct    = active_customers / cohort_size × 100 (tháng 0 luôn = 100%)
--   ci_low, ci_high  = khoảng tin cậy Wilson 95% của retention_pct: cohort nhỏ thì khoảng rộng, đừng tin con số giữa
--   is_complete      = tháng thứ k đã kết thúc hẳn (tháng đang chạy còn tăng, chưa so được)
--
-- Khách = 1 email (customer_key). Đơn không email không thuộc cohort nào. Đơn tính như fct_orders (không test,
-- kể cả huỷ), giống dim_customer, để số khách mỗi cohort khớp customer_summary.
-- Bẫy: Shopify trong kho chỉ có từ 11/2024, nên khách mua lần đầu TRƯỚC đó bị tính vào cohort đầu tiên có trong kho
-- (cohort 2024-11 phình to, % quay lại của nó không đúng nghĩa "khách mới").
with customers as (
    select customer_key, parse_date('%Y-%m', cohort_month) as cohort_start
    from {{ ref('dim_customer') }}
),
sizes as (
    select cohort_start, count(*) as cohort_size from customers group by 1
),
last_month as (
    -- tháng của ngày dữ liệu mới nhất; tháng này chưa hết nên chưa "complete"
    select date_trunc(max(order_date), month) as m from {{ ref('fct_orders') }}
),
grid as (
    -- đủ mọi ô k = 0 .. (tháng cuối − tháng cohort), kể cả ô không ai mua (0%), để bảng tam giác không bị khuyết
    select s.cohort_start, s.cohort_size, k as month_offset
    from sizes s
    cross join last_month l
    cross join unnest(generate_array(0, date_diff(l.m, s.cohort_start, month))) as k
),
activity as (
    select
        c.cohort_start,
        date_diff(date_trunc(o.order_date, month), c.cohort_start, month) as month_offset,
        count(distinct o.customer_key)                                     as active_customers
    from {{ ref('fct_orders') }} o
    join customers c using (customer_key)
    group by 1, 2
),
rates as (
    select
        g.cohort_start,
        g.cohort_size,
        g.month_offset,
        coalesce(a.active_customers, 0)                          as active_customers,
        safe_divide(coalesce(a.active_customers, 0), g.cohort_size) as p
    from grid g
    left join activity a using (cohort_start, month_offset)
)
select
    format_date('%Y-%m', r.cohort_start)                                       as cohort_month,
    r.month_offset,
    r.cohort_size,
    r.active_customers,
    round(100 * r.p, 2)                                                        as retention_pct,
    -- Wilson 95% (z = 1,96): (p + z²/2n ± z·√(p(1−p)/n + z²/4n²)) / (1 + z²/n)
    round(100 * greatest(0, (r.p + 1.96*1.96/(2*r.cohort_size)
        - 1.96 * sqrt(r.p*(1-r.p)/r.cohort_size + 1.96*1.96/(4*r.cohort_size*r.cohort_size)))
        / (1 + 1.96*1.96/r.cohort_size)), 2)                                    as ci_low,
    round(100 * least(1, (r.p + 1.96*1.96/(2*r.cohort_size)
        + 1.96 * sqrt(r.p*(1-r.p)/r.cohort_size + 1.96*1.96/(4*r.cohort_size*r.cohort_size)))
        / (1 + 1.96*1.96/r.cohort_size)), 2)                                    as ci_high,
    date_add(r.cohort_start, interval r.month_offset month) < l.m              as is_complete
from rates r
cross join last_month l
