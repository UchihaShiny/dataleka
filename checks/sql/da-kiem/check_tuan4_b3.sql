-- Tuần 4 B3: kiểm mart_repeat_60d (chạy từng câu trên BigQuery console, thay <project> bằng datae-514203).

-- Câu 1: tỉ lệ mua lần 2 trong 60 ngày theo type đơn đầu (đây là đáp án câu mẫu 3).
select first_type,
       countif(is_eligible)                                        as khach_du_60_ngay,
       countif(repeat_60d)                                         as mua_lan_2,
       round(100 * safe_divide(countif(repeat_60d), countif(is_eligible)), 1) as ti_le_pct,
       countif(is_eligible and is_multi_type)                      as don_dau_nhieu_type
from `datae-514203.gold.mart_repeat_60d`
group by 1
order by khach_du_60_ngay desc;

-- Câu 2: tính lại độc lập từ fct_orders (không qua mart): tổng khách đủ 60 ngày và số mua lần 2 phải khớp câu 1.
with o as (
  select customer_key, order_date,
         row_number() over (partition by customer_key order by created_at, order_id) as rn
  from `datae-514203.gold.fct_orders`
  where customer_key is not null and not is_cancelled
),
f as (select customer_key, order_date as d1 from o where rn = 1),
a as (select date_sub(max(order_date), interval 1 day) as as_of from `datae-514203.gold.fct_orders`)
select countif(f.d1 <= date_sub(a.as_of, interval 60 day))                                as khach_du_60_ngay,
       countif(f.d1 <= date_sub(a.as_of, interval 60 day)
               and exists (select 1 from o where o.customer_key = f.customer_key
                           and date_diff(o.order_date, f.d1, day) between 1 and 60))      as mua_lan_2
from f cross join a;

-- Câu 3: so với dim_customer.is_repeat để thấy độ lệch do bỏ đơn huỷ / cùng ngày / 60 ngày.
select countif(is_repeat) as dim_is_repeat, count(*) as dim_khach,
       (select count(*) from `datae-514203.gold.mart_repeat_60d`) as mart_khach,
       (select countif(has_same_day_extra) from `datae-514203.gold.mart_repeat_60d`) as co_don_cung_ngay
from `datae-514203.gold.dim_customer`;
