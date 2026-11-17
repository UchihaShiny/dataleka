-- Gold: 1 dòng = 1 ngày kinh doanh (giờ Phoenix). Nơi chốt định nghĩa chỉ số, mọi người đọc chung.
-- Dựng từ fact: fct_orders (Shopify), fct_ad_day (Meta), stg_refunds (theo ngày hoàn), email_daily (Klaviyo).
-- Định nghĩa tạm (10/11/2026), chờ context/metrics.md của anh Quang ở cổng khớp số tuần 3:
--   orders  = số đơn Shopify không phải test (kể cả đơn huỷ: cách đếm này khớp 815 đơn 1–7/11 đã đối chiếu)
--   rev     = tổng current_total của các đơn đó (theo ngày ĐẶT; rev ngày cũ giảm dần khi có hoàn)
--   refunds = tiền hoàn theo ngày HOÀN (khác ngày đặt)
--   spend   = tổng spend Meta mọi tài khoản
--   MER     = rev / spend        (đơn và tiền lấy từ Shopify, không dùng số Meta tự nhận)
--   CPO     = spend / orders
with orders as (
    select
        order_date                    as date,
        count(*)                      as orders,
        countif(is_cancelled)         as cancelled_orders,
        countif(is_first_order)       as first_orders,
        sum(rev)                      as rev
    from {{ ref('fct_orders') }}
    group by 1
),

meta as (
    select
        date,
        sum(spend)                    as spend,
        sum(impressions)              as impressions,
        sum(clicks)                   as clicks,
        sum(inline_link_clicks)       as link_clicks,
        sum(meta_purchases)           as meta_purchases,
        sum(meta_purchase_value)      as meta_purchase_value
    from {{ ref('fct_ad_day') }}
    group by 1
),

refunds as (
    -- chỉ hoàn của đơn được tính (không test)
    select r.refund_date as date, sum(r.refund_amount) as refunds
    from {{ ref('stg_refunds') }} r
    join {{ ref('fct_orders') }} o on o.order_id = r.order_id
    group by 1
),

email as (
    select
        date,
        sum(if(channel in ('campaign', 'flow', '(không rõ)'), placed_orders, 0))  as email_orders,
        sum(if(channel in ('campaign', 'flow', '(không rõ)'), placed_value, 0))   as email_value
    from {{ ref('email_daily') }}
    group by 1
),

meta_range as (
    -- Khoảng ngày kho đã nạp Meta. Ngoài khoảng này spend là "chưa có dữ liệu" (null), không phải 0:
    -- trước ngày đầu (chưa gom lịch sử) và sau ngày cuối (chưa nạp ngày mới).
    -- Lỗi tìm ra khi thử MCP 10/11: 9/11 chưa nạp Meta mà hiện spend 0, cpo 0.
    select min(date) as first_date, max(date) as last_date from {{ ref('fct_ad_day') }}
),

days as (
    -- MỌI ngày từ ngày sớm nhất tới muộn nhất, kể cả ngày không có đơn (orders = 0).
    -- Trước đây chỉ có ngày có đơn/spend/hoàn, nên ngày không đơn bị mất và trông như kho thiếu dữ liệu.
    select date
    from unnest(generate_date_array(
        (select least(min(date), (select min(date) from meta)) from orders),
        (select greatest(max(date), (select max(date) from meta)) from orders)
    )) as date
)

select
    d.date,
    coalesce(o.orders, 0)                                                as orders,
    coalesce(o.cancelled_orders, 0)                                      as cancelled_orders,
    coalesce(o.first_orders, 0)                                          as first_orders,
    coalesce(o.rev, 0)                                                   as rev,
    coalesce(r.refunds, 0)                                               as refunds,
    if(d.date between s.first_date and s.last_date, coalesce(m.spend, 0), null)        as spend,
    round(safe_divide(coalesce(o.rev, 0),
          if(d.date between s.first_date and s.last_date, coalesce(m.spend, 0), null)), 4) as mer,
    round(safe_divide(if(d.date between s.first_date and s.last_date, coalesce(m.spend, 0), null),
          nullif(o.orders, 0)), 2)                                                     as cpo,
    m.impressions,
    m.clicks,
    m.link_clicks,
    m.meta_purchases,
    round(safe_divide(m.meta_purchase_value, m.spend), 4)                as meta_roas,
    e.email_orders,
    e.email_value
from days d
cross join meta_range s
left join orders o on o.date = d.date
left join meta m on m.date = d.date
left join refunds r on r.date = d.date
left join email e on e.date = d.date
