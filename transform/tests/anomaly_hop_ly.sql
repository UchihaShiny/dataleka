-- Kiểm mart_anomaly_daily (lỗi thì chặn build). Có dòng ở đây = sai, cột loi cho biết sai gì và ở ngày, chỉ số nào:
--   orders phải khớp daily_performance; gross_sales phải khớp tổng total_price của fct_orders;
--   mốc phải đủ ngày (8 cùng thứ, hoặc 28 với chỉ số hiếm); đủ cả 9 chỉ số (cancel_rate từng mất im lặng); độ rộng > 0 khi có score; không có ngày chưa trọn.
with src as (
  select order_date as date, count(*) as orders, sum(total_price) as gross
  from {{ ref('fct_orders') }} group by 1
)
select concat('lech_orders: ', cast(a.date as string)) as loi, a.value - coalesce(s.orders, 0) as gia_tri
from {{ ref('mart_anomaly_daily') }} a left join src s using (date)
where a.metric = 'orders' and a.value != coalesce(s.orders, 0)
union all
select concat('lech_gross: ', cast(a.date as string)), a.value - coalesce(s.gross, 0)
from {{ ref('mart_anomaly_daily') }} a left join src s using (date)
where a.metric = 'gross_sales' and abs(a.value - coalesce(s.gross, 0)) > 0.01
union all
select concat('moc_thieu: ', metric, ' ', cast(date as string)), n_base
from {{ ref('mart_anomaly_daily') }}
where n_base != if(method = 'nhân theo thứ', {{ var('anomaly_base_weeks') }}, {{ var('anomaly_rare_days') }})
union all
-- event phải đúng lịch sự kiện (ngày có sự kiện mà không ghi, hoặc ghi sai tên)
select concat('event_lech: ', a.metric, ' ', cast(a.date as string)), 0
from {{ ref('mart_anomaly_daily') }} a left join {{ ref('events') }} e using (date)
where coalesce(a.event, '') != coalesce(e.event, '')
union all
select concat('thieu_chi_so: ', m), 0
from unnest(['orders', 'gross_sales', 'spend', 'cpo', 'mer', 'new_share', 'cancel_rate', 'refunds', 'email_orders']) m
where m not in (select distinct metric from {{ ref('mart_anomaly_daily') }})
union all
select concat('do_rong_0: ', metric, ' ', cast(date as string)), scale
from {{ ref('mart_anomaly_daily') }} where score is not null and not scale > 0
union all
select concat('ngay_chua_tron: ', cast(date as string)), 0
from {{ ref('mart_anomaly_daily') }} where date > (select complete_through from {{ ref('load_status') }})
