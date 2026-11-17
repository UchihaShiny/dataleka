-- Kiểm dim_variant (sau dbt build). Dán vào BigQuery Console, bôi đen 1 câu rồi Run.

-- 1. Số tổng KHÔNG ĐỔI khi nối biến thể. Đúng: units 1338, line_revenue 41214.26 (1–7/11), dong_mat = 0.
select sum(quantity) as units, round(sum(line_revenue), 2) as line_revenue,
       countif(variant_id is not null and variant_type is null and device_model is null and size is null) as dong_khong_co_thong_tin_bien_the
from gold.fct_lines where order_date between '2026-11-01' and '2026-11-07';

-- 2. Loại biến thể: có '(chưa ánh xạ)' không? Đúng: không có dòng '(chưa ánh xạ)'.
select sku_prefix, type_option_name, variant_type, count(*) as bien_the
from gold.dim_variant where type_option_name is not null
group by 1, 2, 3 order by 1, 4 desc;

-- 3. Ốp điện thoại 1–7/11: tỉ lệ MagSafe trong khách iPhone (Samsung không có MagSafe nên tách riêng).
select device_brand, variant_type, sum(quantity) as so_luong, round(sum(line_revenue), 2) as doanh_thu,
       round(100 * sum(quantity) / sum(sum(quantity)) over (partition by device_brand), 1) as pct_trong_hang
from gold.fct_lines
where product_line = 'Phone Case' and order_date between '2026-11-01' and '2026-11-07'
group by 1, 2 order by 1, 3 desc;

-- 4. Hoodie AUH 1–7/11: bản dày bán bao nhiêu.
select variant_type, sum(quantity) as so_luong, round(sum(line_revenue), 2) as doanh_thu
from gold.fct_lines
where sku_prefix = 'AUH' and order_date between '2026-11-01' and '2026-11-07'
group by 1 order by 2 desc;
