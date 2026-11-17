-- Gold (mô hình 5, phần XYZ): 1 dòng = 1 mẫu đủ tuổi có bán. Đo mẫu BÁN ĐỀU hay THẤT THƯỜNG (bài học: XYZ).
-- ⚠ Kết quả 12/11: ở cấp mẫu cv PHẦN LỚN LÀ NHIỄU. Mẫu POD bán 1–2 cái/tuần nên riêng may rủi đã cho cv ~0,7–1
-- (Poisson: cv ≈ 1 / √(cái mỗi tuần)); chỉ 147 mẫu đủ dữ liệu, trung vị cv 1,02, chỉ 4 mẫu X. Đọc XYZ ở mart_xyz_group
-- (dòng con, biến thể). Bảng này chỉ để soi riêng mẫu bán nhiều.
--
--   Cửa sổ: 12 tuần TRỌN = 84 ngày cuối của cửa sổ ABC (90 ngày lẻ 6 ngày, tuần thiếu ngày làm lệch số).
--   Mỗi mẫu: doanh thu từng tuần (kể cả tuần 0 đồng), CHỈ tính các tuần mẫu đã mở bán trọn tuần.
--   cv (hệ số biến thiên) = độ lệch chuẩn ÷ trung bình doanh thu tuần.
--   xyz_class: X cv < xyz_x (bán đều) | Y xyz_x–xyz_y | Z > xyz_y (thất thường)
--              | '(chưa đủ dữ liệu)' khi dưới xyz_min_units cái hoặc dưới xyz_min_weeks tuần mở bán
--              (mẫu bán 1–2 cái thì cv luôn cao, tự thành Z: là nhiễu, bài học "CZ gần như là nhiễu").
--   Ngưỡng ở vars dbt_project.yml. Bài học không cho số; 0,5 / 1,0 là ngưỡng hay dùng, xem phân bố thật rồi chỉnh.
-- Kèm abc_class, abc_in_line từ mart_product_abc để ra 9 ô (AX, AY, AZ, ...). Lọc đơn huỷ, dòng không phải sản phẩm
-- (macro is_non_product) y như mart_product_abc.
-- Bẫy: 12 tuần không đủ để tách "mùa vụ đoán trước được" (Y theo bài học) với "bất thường" (Z); ở đây Y/Z chỉ khác
-- nhau về mức dao động. Mẫu được bật ads theo đợt cũng ra Z.
with win as (
    select any_value(as_of_date) as as_of_date,
           date_sub(any_value(as_of_date), interval 83 day) as xyz_start
    from {{ ref('mart_product_abc') }}
),
abc as (
    select product_key, product_title, product_line, product_subline, theme, species, product_url,
           created_date, abc_class, abc_in_line
    from {{ ref('mart_product_abc') }}
    where not is_new and units > 0
),
weeks as (
    select a.product_key, w.xyz_start, k as week_no,
           date_add(w.xyz_start, interval 7 * k day) as week_start
    from abc a
    cross join win w
    cross join unnest(generate_array(0, 11)) as k
    -- chỉ tuần mẫu đã mở bán TRỌN tuần (mẫu đã xoá không biết ngày tạo: coi là mở bán cả 12 tuần)
    where a.created_date is null or a.created_date <= date_add(w.xyz_start, interval 7 * k day)
),
lines as (
    select
        coalesce(cast(l.product_id as string), concat('(đã xoá) ', l.product_title)) as product_key,
        div(date_diff(l.order_date, w.xyz_start, day), 7)                            as week_no,
        l.quantity,
        l.line_revenue
    from {{ ref('fct_lines') }} l
    join {{ ref('fct_orders') }} o using (order_id)
    cross join win w
    where l.order_date between w.xyz_start and w.as_of_date
      and not o.is_cancelled
      and not {{ is_non_product('l.product_title') }}
),
weekly as (
    select wk.product_key, wk.week_no,
           coalesce(sum(li.line_revenue), 0) as week_revenue,
           coalesce(sum(li.quantity), 0)     as week_units
    from weeks wk
    left join lines li using (product_key, week_no)
    group by 1, 2
),
stats as (
    select
        product_key,
        count(*)                          as weeks_live,
        sum(week_units)                   as units_12w,
        sum(week_revenue)                 as revenue_12w,
        avg(week_revenue)                 as mean_week,
        stddev_samp(week_revenue)         as sd_week,
        countif(week_units > 0)           as weeks_with_sales,
        max(week_revenue)                 as max_week
    from weekly
    group by 1
)
select
    a.product_key,
    a.product_title,
    a.product_line,
    a.product_subline,
    a.theme,
    a.species,
    a.product_url,
    a.abc_class,
    a.abc_in_line,
    w.xyz_start,
    w.as_of_date,
    coalesce(s.weeks_live, 0)                                                   as weeks_live,
    coalesce(s.weeks_with_sales, 0)                                             as weeks_with_sales,
    coalesce(s.units_12w, 0)                                                    as units_12w,
    round(coalesce(s.revenue_12w, 0), 2)                                        as revenue_12w,
    round(s.mean_week, 2)                                                       as mean_week,
    round(s.sd_week, 2)                                                         as sd_week,
    round(safe_divide(s.sd_week, s.mean_week), 3)                               as cv,
    round(safe_divide(s.max_week, s.revenue_12w), 3)                            as top_week_share,
    case
        when coalesce(s.units_12w, 0) < {{ var('xyz_min_units') }}
          or coalesce(s.weeks_live, 0) < {{ var('xyz_min_weeks') }}             then '(chưa đủ dữ liệu)'
        when safe_divide(s.sd_week, s.mean_week) < {{ var('xyz_x') }}           then 'X'
        when safe_divide(s.sd_week, s.mean_week) <= {{ var('xyz_y') }}          then 'Y'
        else 'Z'
    end                                                                         as xyz_class
from abc a
cross join win w
left join stats s using (product_key)
