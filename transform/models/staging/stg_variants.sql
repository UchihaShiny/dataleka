-- Silver: 1 dòng = 1 biến thể (size, loại, đời máy) của sản phẩm.
-- Tách lựa chọn theo TÊN trong selected_options (Shopify selectedOptions), không theo vị trí trong title
-- (vị trí "loại" khác nhau giữa các dòng: AUH là "size / loại", TPC là "loại / đời máy") và không tách SKU
-- (SKU có ít nhất 4 kiểu viết). Tên lựa chọn của shop (kiểm 11/11): Size, Interior Weight, Case Type, Model, Title.
with options as (
    select
        variant_id,
        array(
            select as struct json_value(o, '$.name') as name, json_value(o, '$.value') as value
            from unnest(json_query_array(selected_options)) as o
        ) as opts
    from {{ source('raw', 'shopify_product_variants') }}
)

select
    v.variant_id,
    v.product_id,
    v.sku,
    {{ sku_prefix('v.sku') }}                                                           as sku_prefix,
    v.title,
    cast(v.price as numeric)                                                            as price,
    (select value from unnest(o.opts) where name = 'Size' limit 1)                      as size,
    -- lựa chọn mang nghĩa "loại": hoodie dùng Interior Weight, ốp dùng Case Type
    (select name from unnest(o.opts) where name in ('Interior Weight', 'Case Type') limit 1)  as type_option_name,
    (select value from unnest(o.opts) where name in ('Interior Weight', 'Case Type') limit 1) as type_option_value,
    (select value from unnest(o.opts) where name = 'Model' limit 1)                     as device_model,
    v.created_at,
    v.updated_at
from {{ source('raw', 'shopify_product_variants') }} v
left join options o on o.variant_id = v.variant_id
