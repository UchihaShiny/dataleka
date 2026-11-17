-- Gold (tuần 3): 1 dòng = 1 ngày kinh doanh (Phoenix) × 1 product type (product_line). Rev, Spend, ROAS.
--
--   rev   = tổng line_revenue của fct_lines (doanh thu dòng sản phẩm: sau giảm giá và trả hàng, CHƯA gồm ship, thuế).
--           Vì vậy cộng rev mọi type của 1 ngày NHỎ HƠN rev của mart_daily_kpi (rev đơn có ship, thuế).
--   spend = tổng spend fct_ad_day theo ad_product_line (type đọc từ tên campaign, seeds/campaign_types.csv).
--           Cộng spend mọi type (kể cả '(không theo type)') = spend của mart_daily_kpi.
--   roas  = rev / spend của type đó. Null khi spend null hoặc 0.
--
-- Dòng đặc biệt:
--   '(không theo type)': spend của campaign tên kiểu cũ (gần như toàn bộ 1–9/2026), không có rev → roas 0 (không phải null). MCP type_performance không tính dòng này là type lỗ.
--   type có rev mà không chạy ads ngày đó (ví dụ T-Shirt) → spend 0, roas null.
-- ROAS theo type chỉ có nghĩa từ 10/2026 (98,8% spend có type); trước đó phần lớn spend ở '(không theo type)'.
-- Spend null (không phải 0) ngoài khoảng ngày kho đã nạp Meta, giống daily_performance.
with rev as (
    select order_date as date, product_line, sum(line_revenue) as rev
    from {{ ref('fct_lines') }}
    group by 1, 2
),
spend as (
    select date, ad_product_line as product_line, sum(spend) as spend
    from {{ ref('fct_ad_day') }}
    group by 1, 2
),
meta_range as (
    select min(date) as first_date, max(date) as last_date from {{ ref('fct_ad_day') }}
),
joined as (
    -- full outer join: giữ cả type chỉ có rev (không chạy ads) và type chỉ có spend ('(không theo type)')
    select
        coalesce(r.date, s.date)                 as date,
        coalesce(r.product_line, s.product_line) as product_line,
        r.rev,
        s.spend
    from rev r
    full outer join spend s on s.date = r.date and s.product_line = r.product_line
)
select
    j.date,
    j.product_line,
    round(coalesce(j.rev, 0), 2)                                                  as rev,
    if(j.date between m.first_date and m.last_date, round(coalesce(j.spend, 0), 2), null) as spend,
    round(safe_divide(coalesce(j.rev, 0),
          nullif(if(j.date between m.first_date and m.last_date, coalesce(j.spend, 0), null), 0)), 4) as roas
from joined j
cross join meta_range m
