-- Mô hình 2 (RFM): BACKTEST. Kiểm cách chia nhóm có dự đoán được ai mua lại không (bước bài học gọi là
-- "thứ phân biệt phân tích nghiêm túc với chia nhóm cho đẹp").
--
-- Cách làm, cho mỗi mốc d (1/7/2026 và 1/8/2026):
--   1. Tính RFM CHỈ bằng đơn trước ngày d, đúng luật của mart_rfm (as_of = d − 1).
--   2. Xem trong 90 ngày từ d (d tới d + 89) mỗi khách có đơn không huỷ nào không.
--   3. % mua lại theo nhóm, kèm khoảng tin cậy Wilson 95%.
-- Chia nhóm có giá trị nếu: thứ tự % mua lại hợp lý (Champions cao nhất, Đã mất thấp nhất) VÀ giống nhau ở cả 2 mốc.
-- Hai nhóm có khoảng tin cậy chồng nhau nhiều thì tách ra không giúp gì, cân nhắc gộp.
--
-- LƯU Ý: luật và ngưỡng 60 / 180 / 365 ngày dưới đây CHÉP từ transform/models/marts/mart_rfm.sql và vars trong
-- dbt_project.yml. Đổi ở đó thì phải đổi ở đây. Chỉ đọc gold.fct_orders. Mốc + 90 ngày đều trước 10/11/2026.
with moc as (
  select d from unnest([date '2026-07-01', date '2026-08-01']) as d
),
o as (
  select customer_key, order_date, rev
  from gold.fct_orders
  where customer_key is not null and not is_cancelled
),
past as (
  select m.d, o.customer_key, max(o.order_date) as last_order_date, count(*) as frequency, sum(o.rev) as monetary
  from moc m join o on o.order_date < m.d
  group by 1, 2
),
scored as (
  select *,
    date_diff(date_sub(d, interval 1 day), last_order_date, day)          as recency_days,
    ntile(5) over (partition by d order by monetary)                      as m_score
  from past
),
banded as (
  select *,
    case
      when recency_days <= 60  then 'còn nóng'
      when recency_days <= 180 then 'đang nguội'
      when recency_days <= 365 then 'gần mất'
      else 'đã mất'
    end as r_band
  from scored
),
seg as (
  select d, customer_key,
    case
      when r_band = 'đã mất'                       then 'Đã mất'
      when r_band = 'gần mất' and m_score = 5      then 'Không thể để mất'
      when r_band = 'gần mất' and frequency >= 2   then 'Có nguy cơ'
      when frequency >= 3 and r_band = 'còn nóng'  then 'Champions'
      when frequency >= 3                          then 'Loyal'
      when frequency = 2 and r_band = 'còn nóng'   then 'Mới quay lại'
      when frequency = 2                           then 'Cần chú ý'
      when r_band = 'còn nóng'                     then 'Khách mới'
      else 'Ngủ đông'
    end as segment
  from banded
),
future as (
  select distinct m.d, o.customer_key
  from moc m join o on o.order_date >= m.d and o.order_date < date_add(m.d, interval 90 day)
),
rates as (
  select s.d, s.segment, count(*) as n, countif(f.customer_key is not null) as x
  from seg s left join future f using (d, customer_key)
  group by 1, 2
)
select
  d                                                                       as moc,
  segment,
  n                                                                       as so_khach_tai_moc,
  x                                                                       as mua_lai_90_ngay,
  round(100 * x / n, 1)                                                   as pct_mua_lai,
  -- Wilson 95%
  round(100 * greatest(0, (x/n + 1.96*1.96/(2*n) - 1.96*sqrt((x/n)*(1-x/n)/n + 1.96*1.96/(4*n*n))) / (1 + 1.96*1.96/n)), 1) as ci_low,
  round(100 * least(1,  (x/n + 1.96*1.96/(2*n) + 1.96*sqrt((x/n)*(1-x/n)/n + 1.96*1.96/(4*n*n))) / (1 + 1.96*1.96/n)), 1) as ci_high
from rates
order by moc, pct_mua_lai desc;
