-- Mô hình 2 (RFM), bước 1: kiểm mart_rfm (sau dbt build).

-- Câu 1: ngưỡng R có hợp với hành vi thật không? Khoảng cách (ngày) từ đơn 1 tới đơn 2 của khách có quay lại
-- (chỉ đơn không huỷ). Ngưỡng 60 / 180 ngày hợp lý nếu: trung vị (p50) dưới 60, và p90 quanh hoặc dưới 180.
with o as (
  select customer_key, order_date,
         row_number() over (partition by customer_key order by created_at, order_id) as n
  from gold.fct_orders
  where customer_key is not null and not is_cancelled
),
gap as (
  select date_diff(b.order_date, a.order_date, day) as ngay
  from o a join o b on a.customer_key = b.customer_key and a.n = 1 and b.n = 2
)
select
  count(*)                                                 as so_khach_co_don_2,
  approx_quantiles(ngay, 100)[offset(25)]                  as p25_ngay,
  approx_quantiles(ngay, 100)[offset(50)]                  as p50_ngay,
  approx_quantiles(ngay, 100)[offset(75)]                  as p75_ngay,
  approx_quantiles(ngay, 100)[offset(90)]                  as p90_ngay,
  round(100 * countif(ngay <= 60) / count(*), 1)           as pct_trong_60_ngay,
  round(100 * countif(ngay <= 180) / count(*), 1)          as pct_trong_180_ngay
from gap;

-- Câu 2: các nhóm khách. Kỳ vọng: cộng so_khach = số khách có ít nhất 1 đơn không huỷ (câu 3); Khách mới, Ngủ đông
-- đông nhất (phần lớn khách mua 1 lần); Champions ít.
select
  segment,
  count(*)                                                 as so_khach,
  round(100 * count(*) / sum(count(*)) over (), 1)         as pct_khach,
  round(avg(recency_days))                                 as r_tb_ngay,
  round(avg(frequency), 2)                                 as f_tb,
  round(avg(monetary), 2)                                  as m_tb,
  round(100 * sum(monetary) / sum(sum(monetary)) over (), 1) as pct_doanh_thu
from gold.mart_rfm
group by 1
order by so_khach desc;

-- Câu 3: tổng khách khớp dim_customer (khách có ít nhất 1 đơn không huỷ). Kỳ vọng: 2 số bằng nhau.
select
  (select count(*) from gold.mart_rfm)                                  as khach_rfm,
  (select countif(orders_not_cancelled > 0) from gold.dim_customer)     as khach_dim,
  (select any_value(as_of_date) from gold.mart_rfm)                     as as_of_date;
