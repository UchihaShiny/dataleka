-- Silver: 1 dòng = 1 sản phẩm Shopify (chụp lúc nạp; shop tạo sản phẩm mới liên tục).
select
    product_id,
    title,
    handle,
    product_type,
    vendor,
    tags,
    status,
    created_at,
    updated_at
from {{ source('raw', 'shopify_products') }}
