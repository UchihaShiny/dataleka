-- Gold fact: 1 dòng = 1 dòng sản phẩm trong 1 đơn (không tính đơn test).
-- product_line chọn 1 lần ở đây (productType trên dòng; không có thì tra tiền tố SKU; không có thì '(không rõ)'),
-- product_daily đọc lại từ bảng này. Đọc productType ngay trên dòng nên sản phẩm đã xoá khỏi Shopify vẫn có nhóm.
select
    l.line_item_id,
    l.order_id,
    o.order_date,
    o.customer_key,
    l.product_id,
    l.variant_id,
    l.sku,
    l.sku_prefix,
    coalesce(nullif(l.product_type, ''), m.product_line, '(không rõ)')    as product_line,
    coalesce(m.product_subline,
             coalesce(nullif(l.product_type, ''), m.product_line, '(không rõ)'))  as product_subline,  -- dòng con theo tiền tố SKU
    coalesce(p.title, l.title)                                            as product_title,  -- tên hiện tại; sản phẩm đã xoá thì lấy tên lúc đặt
    l.title                                                               as title_at_order, -- tên lúc khách đặt
    l.variant_title,
    p.product_url,                                                        -- null nếu sản phẩm đã xoá khỏi Shopify
    v.size,
    v.variant_type,                                                       -- AirKnit/Fleece/Heavyweight, Standard/MagSafe
    v.is_heavyweight,
    v.device_model,
    v.device_brand,
    l.quantity,
    l.current_quantity,
    l.unit_price,
    l.line_discount,
    l.unit_price_after_discounts,
    l.line_gross_after_discounts,                    -- sau mọi giảm giá, trước trả hàng
    l.line_revenue                                   -- sau mọi giảm giá và trả hàng, chưa ship, thuế
from {{ ref('stg_line_items') }} l
join {{ ref('fct_orders') }} o on o.order_id = l.order_id   -- inner: bỏ dòng của đơn test
left join {{ ref('product_lines') }} m on m.sku_prefix = l.sku_prefix
left join {{ ref('dim_product') }} p on p.product_id = l.product_id
left join {{ ref('dim_variant') }} v on v.variant_id = l.variant_id   -- biến thể đã xoá thì các cột trên null
