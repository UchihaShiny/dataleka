-- Gold (mô hình 5, Pareto / ABC): 1 dòng = 1 mẫu (product_id), xét trong cửa sổ N ngày tới NGÀY ĐÃ TRỌN cuối
-- (macro complete_through, như mart_repeat_60d). 16/11 sửa: bản cũ lấy max(order_date) nên tính lẫn ngày đang dở.
-- 4 lựa chọn theo bài học: đơn vị = mẫu; thước đo = line_revenue (sau giảm giá, trả hàng); cửa sổ 90 ngày (vars);
-- tập hợp = MỌI MẪU ĐANG MỞ BÁN (is_live) kể cả bán 0 cái, cộng mẫu đã xoá/ẩn nhưng có bán trong cửa sổ.
--
--   abc_class      = A: nằm trong 80% doanh thu đầu | B: 80% → 95% | C: 95% → 100% | D: đang mở bán, 0 cái trong cửa sổ
--                    | Mới: mở bán dưới 30 ngày (tách riêng để không phạt oan, như Khách mới ở RFM)
--   abc_in_line    = cùng cách chia nhưng xếp RIÊNG trong từng product_line (Hoodie 60 USD luôn thắng Ornament 20 USD)
--   rev_per_live_day = doanh thu / số ngày mẫu có mở bán trong cửa sổ (so mẫu mới với mẫu cũ cho công bằng)
-- Ngưỡng ở vars (abc_a_share, abc_b_share, abc_new_days, abc_window_days) trong dbt_project.yml.
--
-- Loại khỏi xếp hạng: dòng của đơn HUỶ; dòng KHÔNG PHẢI SẢN PHẨM (Tip, UpCart / Shipping Protection, Gift Card, nhận theo
-- tên, chờ anh Quang chốt). "gift card" phải là cả cụm từ: 12/11 bản đầu khớp nhầm "Seed Gift Cardinal Pair" (ornament thật).
-- Mẫu đã XOÁ khỏi Shopify thì dòng đơn không còn product_id: vẫn tính (bài học), khoá bằng tên lúc đặt (product_key).
-- ABC xếp CHỈ TRONG MẪU ĐỦ TUỔI: A/B/C = 80/15/5% doanh thu của mẫu đủ tuổi; mẫu Mới đứng riêng, không chen vào thứ hạng
-- (12/11 bản đầu cho Mới chen vào nên A chỉ còn 77,2%).
-- Thứ tự cộng dồn: doanh thu giảm dần, hoà thì theo product_key (ổn định giữa các lần build).
-- Bẫy: ABC đo KẾT QUẢ, không đo tiềm năng; nhóm A có thể chỉ là mẫu được chạy ads (chưa nối ad với mẫu).
with as_of as (
    select {{ complete_through() }} as d   -- ngày đã trọn theo lúc nạp (macro complete_through)
),
win as (
    select d as as_of_date, date_sub(d, interval {{ var('abc_window_days') }} - 1 day) as window_start from as_of
),
lines as (
    select
        coalesce(cast(l.product_id as string), concat('(đã xoá) ', l.product_title)) as product_key,
        l.product_id, l.product_line as line_at_order, l.product_title, l.order_id, l.quantity, l.line_revenue
    from {{ ref('fct_lines') }} l
    join {{ ref('fct_orders') }} o using (order_id)
    cross join win w
    where l.order_date between w.window_start and w.as_of_date
      and not o.is_cancelled
      and not {{ is_non_product('l.product_title') }}
),
sales as (
    select
        product_key,
        any_value(product_id)            as product_id,
        any_value(line_at_order)         as line_at_order,
        any_value(product_title)         as title_at_order,
        sum(line_revenue)                as revenue,
        sum(quantity)                    as units,
        count(distinct order_id)         as orders
    from lines
    group by 1
),
universe as (
    -- mẫu đang mở bán (kể cả 0 cái) ∪ mẫu có bán trong cửa sổ (kể cả đã ẩn/xoá)
    select cast(product_id as string) as product_key from {{ ref('dim_product') }}
    where is_live and not {{ is_non_product('title') }}
    union distinct
    select product_key from sales
),
base as (
    select
        u.product_key,
        coalesce(p.product_id, s.product_id)                              as product_id,
        coalesce(p.title, s.title_at_order)                               as product_title,
        coalesce(p.product_line, s.line_at_order, '(không rõ)')           as product_line,
        p.product_subline,
        p.theme,
        p.species,
        p.product_url,
        coalesce(p.is_live, false)                                        as is_live,
        date(p.created_at, 'America/Phoenix')                             as created_date,
        w.as_of_date,
        w.window_start,
        coalesce(s.revenue, 0)                                            as revenue,
        coalesce(s.units, 0)                                              as units,
        coalesce(s.orders, 0)                                             as orders,
        -- tuổi mẫu tới as_of; mẫu đã xoá không biết ngày tạo → coi như đủ cửa sổ
        coalesce(date_diff(w.as_of_date, date(p.created_at, 'America/Phoenix'), day), 9999) as age_days,
        least({{ var('abc_window_days') }},
              coalesce(date_diff(w.as_of_date, date(p.created_at, 'America/Phoenix'), day) + 1, {{ var('abc_window_days') }})) as live_days_in_window
    from universe u
    cross join win w
    left join {{ ref('dim_product') }} p on cast(p.product_id as string) = u.product_key
    left join sales s on s.product_key = u.product_key
),
flagged as (
    select *, age_days < {{ var('abc_new_days') }} as is_new from base
),
ranked as (
    select
        *,
        sum(revenue) over ()                                                          as total_revenue,
        -- cộng dồn chỉ trong cùng nhóm tuổi (đủ tuổi / mới): mẫu Mới không chen vào thứ hạng A/B/C
        sum(revenue) over (partition by is_new)                                       as group_revenue,
        sum(revenue) over (partition by is_new order by revenue desc, product_key
                           rows between unbounded preceding and 1 preceding)          as cum_before,
        sum(revenue) over (partition by is_new, product_line)                         as line_revenue_total,
        sum(revenue) over (partition by is_new, product_line order by revenue desc, product_key
                           rows between unbounded preceding and 1 preceding)          as line_cum_before,
        row_number() over (partition by is_new order by revenue desc, product_key)    as rank_all
    from flagged
)
select
    product_key,
    product_id,
    is_new,
    product_title,
    product_line,
    product_subline,
    theme,
    species,
    product_url,
    is_live,
    created_date,
    age_days,
    as_of_date,
    window_start,
    round(revenue, 2)                                                                 as revenue,
    units,
    orders,
    live_days_in_window,
    round(safe_divide(revenue, live_days_in_window), 2)                               as rev_per_live_day,
    rank_all,
    round(100 * safe_divide(revenue, total_revenue), 4)                               as share_pct,
    round(100 * safe_divide(coalesce(cum_before, 0) + revenue, group_revenue), 2)     as cum_share_pct,
    case
        when is_new                                                                   then 'Mới'
        when units = 0                                                                then 'D'
        when safe_divide(coalesce(cum_before, 0), group_revenue) < {{ var('abc_a_share') }} then 'A'
        when safe_divide(coalesce(cum_before, 0), group_revenue) < {{ var('abc_b_share') }} then 'B'
        else 'C'
    end                                                                               as abc_class,
    case
        when is_new                                                                   then 'Mới'
        when units = 0                                                                then 'D'
        when safe_divide(coalesce(line_cum_before, 0), line_revenue_total) < {{ var('abc_a_share') }} then 'A'
        when safe_divide(coalesce(line_cum_before, 0), line_revenue_total) < {{ var('abc_b_share') }} then 'B'
        else 'C'
    end                                                                               as abc_in_line
from ranked
