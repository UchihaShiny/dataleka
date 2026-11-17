-- Silver: 1 dòng = 1 dòng sản phẩm trong 1 đơn (1 đơn có 1–6 dòng, theo mẫu 7/11).
-- line_revenue = line_net (Shopify priceAfterAllDiscountsBeforeTaxes): tiền dòng sau MỌI giảm giá (cả mã giảm giá
-- cho cả giỏ) và sau trả hàng, CHƯA gồm ship, thuế. Cùng ý nghĩa với rev = current_total của đơn, nên cộng
-- line_revenue luôn nhỏ hơn rev (rev còn ship, thuế).
-- Không dùng discounted_total: nó chỉ trừ giảm giá gắn vào dòng, làm doanh thu dòng 1–7/11 thành 44.622,96,
-- lớn hơn cả rev 44.370,74 (kiểm ngày 10/11). Giữ lại cột đó để đối chiếu.
select
    line_item_id,
    order_id,
    product_id,
    variant_id,
    sku,
    {{ sku_prefix('sku') }}                     as sku_prefix,   -- ULS, TPC, RGO... (SKU nháp DL… lấy phần 2), để ánh xạ dòng con
    product_type,                               -- productType của sản phẩm lúc nạp
    name,
    title,
    variant_title,
    quantity,                                   -- số lượng lúc đặt
    current_quantity,                           -- số lượng sau khi trả/sửa đơn
    cast(original_unit_price as numeric)        as unit_price,
    cast(original_total as numeric)             as original_total,
    cast(total_discount as numeric)             as line_discount,
    cast(discounted_total as numeric)           as discounted_total,          -- chỉ để đối chiếu, xem ghi chú trên
    cast(unit_price_after_discounts as numeric) as unit_price_after_discounts,
    cast(unit_price_after_discounts as numeric) * quantity as line_gross_after_discounts, -- trước trả hàng
    cast(line_net as numeric)                   as line_revenue               -- sau mọi giảm giá và trả hàng
from {{ source('raw', 'shopify_order_line_items') }}
