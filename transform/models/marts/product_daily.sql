-- Gold: 1 dòng = 1 ngày kinh doanh (Phoenix) × 1 dòng sản phẩm × 1 dòng con. Dựng từ fct_lines (đơn không test).
-- Cộng theo product_line (nhóm lớn) thì ra đúng số cũ; chia theo product_subline để thấy Sun Hoodie, Glass/Ceramic
-- Ornament... tách khỏi nhóm lớn.
-- line_revenue chưa gồm ship, thuế: cộng các dòng sản phẩm của 1 ngày sẽ nhỏ hơn rev của daily_performance.
select
    order_date                           as date,
    product_line,
    product_subline,
    count(distinct order_id)             as orders,
    sum(quantity)                        as units,
    sum(current_quantity)                as current_units,
    sum(line_revenue)                    as line_revenue
from {{ ref('fct_lines') }}
group by 1, 2, 3
