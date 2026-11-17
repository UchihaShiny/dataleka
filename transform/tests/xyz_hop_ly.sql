-- Kiểm mart_product_xyz hợp lý (lỗi thì chặn build). Có dòng ở đây = sai:
--   đủ dữ liệu mà không có cv; xếp X/Y/Z mà dưới ngưỡng số cái / số tuần; weeks_live vượt 12;
--   tổng doanh thu tuần không khớp số tuần có bán (doanh thu > 0 mà weeks_with_sales = 0).
select product_key, xyz_class, cv, units_12w, weeks_live, weeks_with_sales, revenue_12w
from {{ ref('mart_product_xyz') }}
where (xyz_class in ('X', 'Y', 'Z') and cv is null)
   or (xyz_class in ('X', 'Y', 'Z') and (units_12w < {{ var('xyz_min_units') }} or weeks_live < {{ var('xyz_min_weeks') }}))
   or weeks_live > 12
   or (revenue_12w > 0 and weeks_with_sales = 0)
