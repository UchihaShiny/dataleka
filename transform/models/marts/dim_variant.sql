-- Gold dim: 1 dòng = 1 biến thể. Loại (variant_type) chuẩn hoá qua seeds/variant_types.csv.
--   variant_type null           = biến thể không có lựa chọn "loại" (áo chỉ có size, ornament không có lựa chọn)
--   variant_type '(chưa ánh xạ)' = có lựa chọn loại nhưng giá trị chưa có trong seed → thêm vào seed
-- device_brand chỉ có ở sản phẩm có lựa chọn Model (ốp điện thoại TPC, ốp AirPods APC).
select
    v.variant_id,
    v.product_id,
    v.sku,
    v.sku_prefix,
    v.title,
    v.price,
    v.size,
    v.type_option_name,
    v.type_option_value,                                            -- giá trị gốc, để tra khi lệch
    case
        when v.type_option_value is null then null
        else coalesce(t.variant_type, '(chưa ánh xạ)')
    end                                                             as variant_type,
    t.is_heavyweight,
    v.device_model,
    case
        when starts_with(v.device_model, 'iPhone')  then 'iPhone'
        when starts_with(v.device_model, 'Samsung') then 'Samsung'
        when starts_with(v.device_model, 'AirPods') then 'AirPods'
        when v.device_model is not null             then 'khác'
    end                                                             as device_brand
from {{ ref('stg_variants') }} v
left join {{ ref('variant_types') }} t
    on t.option_name = v.type_option_name and t.option_value = v.type_option_value
