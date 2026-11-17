-- Xem shop đặt TÊN lựa chọn biến thể thế nào, theo tiền tố SKU (sau khi nạp Shopify với selectedOptions).
-- Dán vào BigQuery Console, bôi đen 1 câu rồi Run.

-- 1. Mỗi tiền tố dùng những tên lựa chọn nào, bao nhiêu giá trị khác nhau, ví dụ vài giá trị.
select
  upper(substr(v.sku, 1, 3))                                   as sku_prefix,
  json_value(o, '$.name')                                      as ten_lua_chon,
  count(distinct json_value(o, '$.value'))                     as so_gia_tri,
  array_to_string(array_agg(distinct json_value(o, '$.value') limit 6), ' | ') as vi_du,
  count(*)                                                     as bien_the
from raw.shopify_product_variants v,
     unnest(json_query_array(v.selected_options)) as o
where upper(substr(v.sku, 1, 3)) in ('AUH', 'TPC', 'ULS', 'RGO', 'SSS', 'MHL', 'AUX', 'APC', 'RCO')
group by 1, 2
order by 1, bien_the desc;

-- 2. Mọi tên lựa chọn trong toàn shop (để biết có bao nhiêu kiểu đặt tên).
select json_value(o, '$.name') as ten_lua_chon, count(*) as bien_the
from raw.shopify_product_variants v, unnest(json_query_array(v.selected_options)) as o
group by 1 order by 2 desc;
