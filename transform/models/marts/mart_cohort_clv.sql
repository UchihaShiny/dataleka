-- Gold (mô hình 3, CLV cấp 1 = CLV lịch sử): 1 dòng = 1 cohort (tháng mua đầu) × 1 tháng thứ k.
-- Ô = doanh thu CỘNG DỒN trên mỗi khách của cohort, từ tháng 0 tới hết tháng thứ k. Là số thật đã xảy ra, không dự đoán.
--
--   cohort_size          = số khách của cohort (như mart_cohort_retention)
--   avg_cum_rev          = trung bình doanh thu cộng dồn mỗi khách tới hết tháng k (CLV lịch sử k+1 tháng)
--   median_cum_rev       = trung vị: "khách điển hình" (CLV lệch phải, trung bình bị vài khách lớn kéo lên)
--   ci_low, ci_high      = khoảng tin cậy 95% của avg_cum_rev (trung bình ± 1,96 × độ lệch chuẩn / √n)
--   first_month_rev      = avg_cum_rev ở tháng 0 (giá trị tháng đầu, chủ yếu là đơn đầu)
--   multiple_of_first    = avg_cum_rev / first_month_rev: CLV gấp bao nhiêu lần tháng đầu (bài học dự đoán ~1,1–1,3 ở 12 tháng)
--   is_complete          = tháng k đã kết thúc
--
-- Doanh thu = rev (current_total, đã trừ hoàn), CHƯA trừ giá vốn: đây là CLV DOANH THU, trông đẹp hơn CLV lợi nhuận.
-- Khách, cohort, đơn tính đúng như mart_cohort_retention (cohort từ dim_customer, đơn của fct_orders, kể cả huỷ; đơn huỷ
-- có rev ~0 nên gần như không đổi số).
-- Bẫy: shop gần như chưa có khách trước 2026 (cohort 1/2026 có 4 khách); cohort đủ 12 tháng đều rất nhỏ, nên CLV 12 tháng
-- chưa đo đáng tin. Đọc ở mốc mà cohort lớn (từ 4/2026) đã có.
with customers as (
    select customer_key, parse_date('%Y-%m', cohort_month) as cohort_start
    from {{ ref('dim_customer') }}
),
last_month as (
    select date_trunc(max(order_date), month) as m from {{ ref('fct_orders') }}
),
customer_k as (
    -- mỗi khách × mọi tháng k từ 0 tới tháng dữ liệu cuối, kể cả tháng không mua (cộng dồn giữ nguyên)
    select c.customer_key, c.cohort_start, k as month_offset
    from customers c
    cross join last_month l
    cross join unnest(generate_array(0, date_diff(l.m, c.cohort_start, month))) as k
),
orders as (
    select
        o.customer_key,
        date_diff(date_trunc(o.order_date, month), c.cohort_start, month) as order_offset,
        o.rev
    from {{ ref('fct_orders') }} o
    join customers c using (customer_key)
),
cum as (
    select ck.cohort_start, ck.month_offset, ck.customer_key, coalesce(sum(o.rev), 0) as cum_rev
    from customer_k ck
    left join orders o on o.customer_key = ck.customer_key and o.order_offset <= ck.month_offset
    group by 1, 2, 3
),
agg as (
    select
        cohort_start,
        month_offset,
        count(*)                                     as cohort_size,
        avg(cum_rev)                                 as avg_cum_rev,
        approx_quantiles(cum_rev, 100)[offset(50)]   as median_cum_rev,
        stddev_samp(cum_rev)                         as sd_cum_rev
    from cum
    group by 1, 2
)
select
    format_date('%Y-%m', a.cohort_start)                                            as cohort_month,
    a.month_offset,
    a.cohort_size,
    round(a.avg_cum_rev, 2)                                                         as avg_cum_rev,
    round(a.median_cum_rev, 2)                                                      as median_cum_rev,
    round(greatest(0, a.avg_cum_rev - 1.96 * coalesce(a.sd_cum_rev, 0) / sqrt(a.cohort_size)), 2) as ci_low,
    round(a.avg_cum_rev + 1.96 * coalesce(a.sd_cum_rev, 0) / sqrt(a.cohort_size), 2)              as ci_high,
    round(first_value(a.avg_cum_rev) over (partition by a.cohort_start order by a.month_offset), 2) as first_month_rev,
    round(safe_divide(a.avg_cum_rev,
          first_value(a.avg_cum_rev) over (partition by a.cohort_start order by a.month_offset)), 3) as multiple_of_first,
    date_add(a.cohort_start, interval a.month_offset month) < l.m                   as is_complete
from agg a
cross join last_month l
