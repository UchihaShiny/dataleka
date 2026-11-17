-- Gold (mô hình 5, XYZ CẤP GỘP): 1 dòng = 1 nhóm ở 1 cấp (cap_do = 'dòng con' hoặc 'biến thể').
-- Vì sao gộp (12/11): ở cấp từng mẫu, mẫu POD chỉ bán 1–2 cái/tuần nên riêng may rủi đã cho cv ~0,7–1
-- (Poisson: cv ≈ 1 / √(cái mỗi tuần)); chỉ 4 mẫu đạt X. Bài học liệt kê đơn vị: mẫu, dòng con, chủ đề, loài, biến thể;
-- Huy Anh chọn dòng con + biến thể. Gộp lên thì số cái mỗi tuần đủ lớn, cv đo được hành vi thật.
--
--   dòng con : product_subline (Performance Long Sleeve, Sun Hoodie, Glass Ornament...), nhom = product_subline
--   biến thể : variant_type, CHỈ có ở hoodie AUH (AirKnit / Fleece / Heavyweight) và ốp TPC (MagSafe / Standard);
--              nhom = product_line · variant_type để không lẫn giữa các dòng
--   Cửa sổ: 12 tuần trọn như mart_product_xyz. Mỗi nhóm chỉ tính các tuần BẮT ĐẦU SAU lần bán đầu tiên của nhóm
--   (cả lịch sử), để dòng mới ra giữa cửa sổ không bị xếp Z oan vì các tuần 0 đồng. Tuần chứa lần bán đầu (bán chưa
--   trọn tuần) bị bỏ, nên với nhóm ra đời trong cửa sổ revenue_12w nhỏ hơn tổng thật một chút (xem first_sale_date).
--   cv = độ lệch chuẩn ÷ trung bình doanh thu tuần; noise_cv = 1 / √(cái trung bình mỗi tuần) là mức cv
--   chỉ do may rủi. cv gần noise_cv = dao động chủ yếu là ngẫu nhiên.
--   trend_ratio = doanh thu TB 4 tuần cuối ÷ 4 tuần đầu: cv cao có thể chỉ vì đang tăng (vào mùa) hay giảm, không
--   phải thất thường.
--   xyz_class: X cv < xyz_x | Y xyz_x–xyz_y | Z > xyz_y | '(chưa đủ dữ liệu)' khi < xyz_group_min_weekly_units cái
--   mỗi tuần (trung bình) hoặc < xyz_min_weeks tuần.
-- Lọc đơn huỷ, dòng không phải sản phẩm (macro is_non_product), như mart_product_abc.
with win as (
    select any_value(as_of_date) as as_of_date,
           date_sub(any_value(as_of_date), interval 83 day) as xyz_start
    from {{ ref('mart_product_abc') }}
),
lines as (
    select l.order_date, l.product_line, l.product_subline, l.variant_type, l.quantity, l.line_revenue
    from {{ ref('fct_lines') }} l
    join {{ ref('fct_orders') }} o using (order_id)
    where not o.is_cancelled
      and not {{ is_non_product('l.product_title') }}
),
tagged as (
    -- mỗi dòng đơn vào 1 nhóm ở cấp dòng con, và (nếu có variant_type) 1 nhóm ở cấp biến thể
    select 'dòng con' as cap_do, product_subline as nhom, product_line, order_date, quantity, line_revenue
    from lines where product_subline is not null
    union all
    select 'biến thể', concat(product_line, ' · ', variant_type), product_line, order_date, quantity, line_revenue
    from lines where variant_type is not null
),
first_sale as (
    select cap_do, nhom, any_value(product_line) as product_line, min(order_date) as first_sale_date
    from tagged group by 1, 2
),
weeks as (
    select f.cap_do, f.nhom, f.product_line, f.first_sale_date, k as week_no
    from first_sale f
    cross join win w
    cross join unnest(generate_array(0, 11)) as k
    where f.first_sale_date <= date_add(w.xyz_start, interval 7 * k day)
),
in_window as (
    select t.cap_do, t.nhom, div(date_diff(t.order_date, w.xyz_start, day), 7) as week_no,
           t.quantity, t.line_revenue
    from tagged t cross join win w
    where t.order_date between w.xyz_start and w.as_of_date
),
weekly as (
    select wk.cap_do, wk.nhom, wk.product_line, wk.first_sale_date, wk.week_no,
           coalesce(sum(i.line_revenue), 0) as week_revenue,
           coalesce(sum(i.quantity), 0)     as week_units
    from weeks wk
    left join in_window i using (cap_do, nhom, week_no)
    group by 1, 2, 3, 4, 5
),
stats as (
    select
        cap_do, nhom, any_value(product_line)                 as product_line,
        any_value(first_sale_date)                            as first_sale_date,
        count(*)                                              as weeks_live,
        sum(week_units)                                       as units_12w,
        sum(week_revenue)                                     as revenue_12w,
        avg(week_units)                                       as mean_week_units,
        avg(week_revenue)                                     as mean_week_revenue,
        stddev_samp(week_revenue)                             as sd_week_revenue,
        avg(if(week_no >= 8, week_revenue, null))             as last4_mean,
        avg(if(week_no <= 3, week_revenue, null))             as first4_mean
    from weekly
    group by 1, 2
)
select
    s.cap_do,
    s.nhom,
    s.product_line,
    s.first_sale_date,
    w.xyz_start,
    w.as_of_date,
    s.weeks_live,
    s.units_12w,
    round(s.revenue_12w, 2)                                              as revenue_12w,
    round(s.mean_week_units, 1)                                          as mean_week_units,
    round(s.mean_week_revenue, 2)                                        as mean_week_revenue,
    round(safe_divide(s.sd_week_revenue, s.mean_week_revenue), 3)        as cv,
    round(safe_divide(1, sqrt(nullif(s.mean_week_units, 0))), 3)         as noise_cv,
    round(safe_divide(s.last4_mean, s.first4_mean), 2)                   as trend_ratio,
    case
        when s.mean_week_units < {{ var('xyz_group_min_weekly_units') }}
          or s.weeks_live < {{ var('xyz_min_weeks') }}                    then '(chưa đủ dữ liệu)'
        when safe_divide(s.sd_week_revenue, s.mean_week_revenue) < {{ var('xyz_x') }}  then 'X'
        when safe_divide(s.sd_week_revenue, s.mean_week_revenue) <= {{ var('xyz_y') }} then 'Y'
        else 'Z'
    end                                                                  as xyz_class
from stats s
cross join win w
