-- Silver: 1 dòng = 1 ngày × 1 ad Meta. date đã là ngày theo múi giờ tài khoản (GMT-7, trùng Phoenix).
-- Tách cột actions (JSON) thành các bước phễu. Mỗi bước chỉ lấy đúng 1 tên action_type (macro meta_action),
-- vì một sự kiện nằm dưới tới 8 tên (purchase, omni_purchase, offsite_conversion.fb_pixel_purchase...).
select
    ad_account_id,
    date,
    campaign_id,
    campaign_name,
    adset_id,
    adset_name,
    ad_id,
    ad_name,
    cast(spend as numeric)                                   as spend,
    impressions,
    clicks,
    inline_link_clicks,
    reach,                                                   -- số theo ngày, KHÔNG cộng qua ngày hay qua ad
    {{ meta_action('actions', 'view_content') }}             as meta_view_content,
    {{ meta_action('actions', 'add_to_cart') }}              as meta_add_to_cart,
    {{ meta_action('actions', 'initiate_checkout') }}        as meta_initiate_checkout,
    {{ meta_action('actions', 'purchase') }}                 as meta_purchases,       -- Meta tự nhận, không dùng cho MER/CPO
    {{ meta_action('action_values', 'purchase') }}           as meta_purchase_value   -- Meta tự nhận, chỉ để so trong kênh
from {{ source('raw', 'meta_ad_insights_daily') }}
