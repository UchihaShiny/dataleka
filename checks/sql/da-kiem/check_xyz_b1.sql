-- Mô hình 5, XYZ bước 1: kiểm mart_product_xyz (sau dbt build).

-- Câu 1: khớp nguồn. Tổng doanh thu 12 tuần = fct_lines cùng 84 ngày (bỏ huỷ, bỏ Tip / Gift Card...), CHỈ các mẫu có
-- trong bảng XYZ. Kỳ vọng chenh nhỏ: chỉ lệch do doanh thu ở tuần mẫu CHƯA mở bán trọn (bị loại khỏi cv có chủ đích).
with w as (select any_value(xyz_start) as s, any_value(as_of_date) as e from gold.mart_product_xyz),
src as (
  select sum(l.line_revenue) as tien
  from gold.fct_lines l join gold.fct_orders o using (order_id), w
  where l.order_date between w.s and w.e and not o.is_cancelled
    and not regexp_contains(lower(coalesce(l.product_title, '')), r'^tip$|upcart|shipping protection|\bgift card\b')
    and coalesce(cast(l.product_id as string), concat('(đã xoá) ', l.product_title))
        in (select product_key from gold.mart_product_xyz)
)
select (select s from w) as tu_ngay, (select e from w) as toi_ngay,
       (select round(sum(revenue_12w), 2) from gold.mart_product_xyz) as tong_xyz,
       round(src.tien, 2) as tong_nguon,
       round((select sum(revenue_12w) from gold.mart_product_xyz) - src.tien, 2) as chenh
from src;

-- Câu 2: phân bố cv của các mẫu đủ dữ liệu (để xem ngưỡng 0,5 / 1,0 có hợp không).
select
  count(*)                                       as mau_du_du_lieu,
  approx_quantiles(cv, 100)[offset(10)]          as p10,
  approx_quantiles(cv, 100)[offset(25)]          as p25,
  approx_quantiles(cv, 100)[offset(50)]          as p50,
  approx_quantiles(cv, 100)[offset(75)]          as p75,
  approx_quantiles(cv, 100)[offset(90)]          as p90
from gold.mart_product_xyz
where xyz_class != '(chưa đủ dữ liệu)';

-- Câu 3: bảng 9 ô ABC × XYZ (số mẫu / % doanh thu 12 tuần). Bài học: AX = xương sống, AZ = bán lớn theo đợt, CZ = nhiễu.
select
  abc_class,
  countif(xyz_class = 'X')                                                    as X,
  countif(xyz_class = 'Y')                                                    as Y,
  countif(xyz_class = 'Z')                                                    as Z,
  countif(xyz_class = '(chưa đủ dữ liệu)')                                     as chua_du,
  round(100 * sum(if(xyz_class = 'X', revenue_12w, 0)) / sum(revenue_12w), 1) as pct_dt_X,
  round(100 * sum(if(xyz_class = 'Y', revenue_12w, 0)) / sum(revenue_12w), 1) as pct_dt_Y,
  round(100 * sum(if(xyz_class = 'Z', revenue_12w, 0)) / sum(revenue_12w), 1) as pct_dt_Z
from gold.mart_product_xyz
group by 1
order by 1;

-- Câu 4: soi mẫu. 3 mẫu A có cv thấp nhất (AX) và 3 mẫu A có cv cao nhất (AZ), kèm doanh thu từng tuần,
-- để nhìn bằng mắt xem nhãn có đúng là "đều" và "theo đợt" không.
with pick as (
  (select product_key, product_title, cv, 'AX thấp nhất' as loai from gold.mart_product_xyz
   where abc_class = 'A' and xyz_class != '(chưa đủ dữ liệu)' order by cv limit 3)
  union all
  (select product_key, product_title, cv, 'AZ cao nhất' from gold.mart_product_xyz
   where abc_class = 'A' and xyz_class != '(chưa đủ dữ liệu)' order by cv desc limit 3)
),
w as (select any_value(xyz_start) as s from gold.mart_product_xyz)
select p.loai, p.product_title, p.cv,
  string_agg(cast(round(coalesce(t.tien, 0)) as string), ' | ' order by k) as doanh_thu_12_tuan
from pick p cross join w cross join unnest(generate_array(0, 11)) as k
left join (
  select coalesce(cast(l.product_id as string), concat('(đã xoá) ', l.product_title)) as product_key,
         div(date_diff(l.order_date, w.s, day), 7) as k, sum(l.line_revenue) as tien
  from gold.fct_lines l join gold.fct_orders o using (order_id), w
  where l.order_date >= w.s and not o.is_cancelled
  group by 1, 2
) t on t.product_key = p.product_key and t.k = k
group by 1, 2, 3
order by 1, 3;
