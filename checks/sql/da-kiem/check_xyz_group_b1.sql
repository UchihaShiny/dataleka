-- Mô hình 5, XYZ cấp gộp, bước 1: kiểm mart_xyz_group (sau dbt build).

-- Câu 1: toàn bộ bảng. Đọc theo từng nhóm: cv so với noise_cv (gần nhau = chủ yếu là may rủi),
-- trend_ratio (khác 1 nhiều = cv cao vì đang vào/ra mùa chứ không phải thất thường).
select cap_do, nhom, xyz_class, weeks_live, units_12w, revenue_12w, mean_week_units,
       cv, noise_cv, trend_ratio
from gold.mart_xyz_group
order by cap_do, revenue_12w desc;

-- Câu 2: soi doanh thu từng tuần của 6 nhóm lớn nhất cấp dòng con (để nhìn bằng mắt nhãn X/Y/Z có đúng không).
with top6 as (
  select nhom, xyz_class, cv from gold.mart_xyz_group
  where cap_do = 'dòng con' order by revenue_12w desc limit 6
),
w as (select any_value(xyz_start) as s, any_value(as_of_date) as e from gold.mart_xyz_group),
tuan as (
  select l.product_subline as nhom, div(date_diff(l.order_date, w.s, day), 7) as k, sum(l.line_revenue) as tien
  from gold.fct_lines l join gold.fct_orders o using (order_id), w
  where l.order_date between w.s and w.e and not o.is_cancelled
  group by 1, 2
)
select t6.nhom, t6.xyz_class, t6.cv,
       string_agg(cast(round(coalesce(tu.tien, 0)) as string), ' | ' order by k) as doanh_thu_12_tuan
from top6 t6 cross join unnest(generate_array(0, 11)) as k
left join tuan tu on tu.nhom = t6.nhom and tu.k = k
group by 1, 2, 3
order by t6.cv;

-- Câu 3: nhóm ra đời TRONG cửa sổ 12 tuần (tuần đầu chưa trọn bị bỏ khỏi cv và revenue_12w).
select cap_do, nhom, first_sale_date, weeks_live, revenue_12w, xyz_class
from gold.mart_xyz_group
where first_sale_date > xyz_start
order by first_sale_date;
