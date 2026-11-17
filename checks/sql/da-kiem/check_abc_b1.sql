-- Mô hình 5 (Pareto / ABC), bước 1: kiểm mart_product_abc (sau dbt build).

-- Câu 1: khớp nguồn. Tổng revenue của bảng = tổng line_revenue fct_lines cùng cửa sổ, trừ đơn huỷ và dòng không phải
-- sản phẩm. Kỳ vọng chenh = 0. Cột bi_tach cho biết bao nhiêu tiền là UpCart / Gift Card... đã bị tách ra.
with w as (select any_value(window_start) as s, any_value(as_of_date) as e from gold.mart_product_abc),
src as (
  select
    sum(if(not o.is_cancelled
           and not regexp_contains(lower(coalesce(l.product_title, '')), r'^tip$|upcart|shipping protection|\bgift card\b'),
           l.line_revenue, 0)) as giu,
    sum(if(not o.is_cancelled
           and regexp_contains(lower(coalesce(l.product_title, '')), r'^tip$|upcart|shipping protection|\bgift card\b'),
           l.line_revenue, 0)) as bi_tach,
    sum(if(o.is_cancelled, l.line_revenue, 0)) as don_huy
  from gold.fct_lines l join gold.fct_orders o using (order_id), w
  where l.order_date between w.s and w.e
)
select (select s from w) as tu_ngay, (select e from w) as toi_ngay,
       (select round(sum(revenue), 2) from gold.mart_product_abc) as tong_abc,
       round(src.giu, 2) as tong_nguon, round((select sum(revenue) from gold.mart_product_abc) - src.giu, 2) as chenh,
       round(src.bi_tach, 2) as bi_tach, round(src.don_huy, 2) as don_huy
from src;

-- Câu 2: những gì bị tách vì không phải sản phẩm (xem có đúng là UpCart, Gift Card... không, có tách nhầm mẫu thật không).
select l.product_title, count(*) as so_dong, round(sum(l.line_revenue), 2) as tien
from gold.fct_lines l join gold.fct_orders o using (order_id)
where not o.is_cancelled
  and l.order_date >= (select any_value(window_start) from gold.mart_product_abc)
  and regexp_contains(lower(coalesce(l.product_title, '')), r'^tip$|upcart|shipping protection|\bgift card\b')
group by 1 order by tien desc;

-- Câu 3: bảng ABC. % số mẫu và % doanh thu từng nhóm (so với bảng minh hoạ trong bài: A ~5% mẫu / 80% doanh thu).
select
  abc_class,
  count(*)                                                     as so_mau,
  round(100 * count(*) / sum(count(*)) over (), 1)             as pct_mau,
  round(sum(revenue), 2)                                       as doanh_thu,
  round(100 * sum(revenue) / sum(sum(revenue)) over (), 1)     as pct_doanh_thu,
  round(avg(units), 1)                                         as cai_tb
from gold.mart_product_abc
group by 1
order by case abc_class when 'A' then 1 when 'B' then 2 when 'C' then 3 when 'D' then 4 else 5 end;

-- Câu 4: độ tập trung. Top 1% / 5% / 10% mẫu ĐỦ TUỔI có bán chiếm bao nhiêu % doanh thu của nhóm đó.
with s as (
  select revenue, row_number() over (order by revenue desc) as r, count(*) over () as n
  from gold.mart_product_abc where units > 0 and not is_new
)
select max(n) as mau_co_ban,
  round(100 * sum(if(r <= n * 0.01, revenue, 0)) / sum(revenue), 1) as top1pct,
  round(100 * sum(if(r <= n * 0.05, revenue, 0)) / sum(revenue), 1) as top5pct,
  round(100 * sum(if(r <= n * 0.10, revenue, 0)) / sum(revenue), 1) as top10pct
from s;

-- Câu 5: nhóm Mới có thật là mẫu mới không? Số mẫu theo ngày tạo (created_date) trong 60 ngày gần nhất.
-- Nếu hàng nghìn mẫu dồn vào 1–2 ngày thì có thể created_at bị đặt lại khi nhập hàng loạt, nhãn Mới sẽ sai.
select created_date, count(*) as so_mau, countif(units > 0) as co_ban, round(sum(revenue), 2) as doanh_thu
from gold.mart_product_abc
where created_date >= date_sub((select any_value(as_of_date) from gold.mart_product_abc), interval 60 day)
group by 1 order by so_mau desc
limit 15;
