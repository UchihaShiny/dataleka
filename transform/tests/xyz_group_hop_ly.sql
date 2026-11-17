-- Kiểm mart_xyz_group (lỗi thì chặn build). Có dòng ở đây = sai, cột loi cho biết sai gì và ở nhóm nào:
--   dòng con ĐÃ CÓ BÁN TRƯỚC cửa sổ 12 tuần: doanh thu 12 tuần phải khớp nguồn từng nhóm (nhóm ra đời trong cửa sổ
--   bỏ tuần đầu chưa trọn, có chủ đích, nên không so);
--   X/Y/Z phải đủ ngưỡng số cái và số tuần; weeks_live ≤ 12.
with w as (select any_value(xyz_start) as s, any_value(as_of_date) as e from {{ ref('mart_xyz_group') }}),
src as (
  select l.product_subline as nhom, sum(l.line_revenue) as tien
  from {{ ref('fct_lines') }} l join {{ ref('fct_orders') }} o using (order_id), w
  where l.order_date between w.s and w.e and not o.is_cancelled and not {{ is_non_product('l.product_title') }}
  group by 1
)
select concat('lech_doanh_thu: ', g.nhom) as loi, g.revenue_12w - coalesce(src.tien, 0) as gia_tri
from {{ ref('mart_xyz_group') }} g
cross join w
left join src on src.nhom = g.nhom
where g.cap_do = 'dòng con' and g.first_sale_date <= w.s
  and abs(g.revenue_12w - coalesce(src.tien, 0)) > 1
union all
select concat('xep_sai: ', nhom), mean_week_units from {{ ref('mart_xyz_group') }}
where xyz_class in ('X', 'Y', 'Z')
  and (mean_week_units < {{ var('xyz_group_min_weekly_units') }} or weeks_live < {{ var('xyz_min_weeks') }})
union all
select concat('tuan_vuot: ', nhom), weeks_live from {{ ref('mart_xyz_group') }} where weeks_live > 12
