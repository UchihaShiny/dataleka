-- Gold fact: 1 dòng = 1 ngày × 1 ad Meta, kèm thông tin cây ad (creative, objective, tuổi ad).
-- LEFT JOIN sang cây ad: ad đã xoá (khoảng 51 dòng 5–9/2026) không có trong cây ad nhưng vẫn giữ số liệu.
-- Không cộng reach qua ngày hay qua ad.
--
-- ad_product_line (tuần 3): product type đọc từ TÊN CAMPAIGN, để chia spend theo type (mart_type_day).
--   Tên kiểu mới '<Format>-<Đích>_<Type>_<Audience>' (bắt đầu Catalog- / Static-, dùng từ 9/2026):
--     campaign_type = phần thứ 2 khi cắt theo '_', tra seeds/campaign_types.csv → product_line;
--     không có trong seed → '(chưa gán)' (test cảnh báo, cần thêm dòng seed).
--   Tên kiểu cũ (1–9/2026, ví dụ Scale:CBO:Lowest Cost_Catalog_ULS ...) → '(không theo type)': tên không nói
--     bán type gì (Fishing, Creative là chủ đề/chiến thuật), nên không đoán.
with ads as (
select
    d.ad_account_id,
    d.date,
    d.campaign_id,
    d.campaign_name,
    d.adset_id,
    d.adset_name,
    d.ad_id,
    d.ad_name,
    a.creative_id,
    a.campaign_objective,
    a.effective_status_now,                                              -- trạng thái hôm nay, không phải của ngày này
    date(a.created_time, 'America/Phoenix')                              as ad_created_date,
    date_diff(d.date, date(a.created_time, 'America/Phoenix'), day)      as ad_age_days,
    a.ad_id is not null                                                  as in_ad_tree,
    d.spend,
    d.impressions,
    d.clicks,
    d.inline_link_clicks,
    d.reach,
    d.meta_view_content,
    d.meta_add_to_cart,
    d.meta_initiate_checkout,
    d.meta_purchases,
    d.meta_purchase_value
from {{ ref('stg_meta_ad_day') }} d
left join {{ ref('stg_meta_ads') }} a on a.ad_id = d.ad_id
),
typed as (
    select
        *,
        coalesce(regexp_contains(campaign_name, r'^(Catalog|Static)-'), false)   as is_typed_name,
        if(coalesce(regexp_contains(campaign_name, r'^(Catalog|Static)-'), false),
           split(campaign_name, '_')[safe_offset(1)], null)                        as campaign_type
    from ads
)
select
    t.*,
    case
        when not t.is_typed_name then '(không theo type)'
        else coalesce(c.product_line, '(chưa gán)')
    end                                                                            as ad_product_line
from typed t
left join {{ ref('campaign_types') }} c on c.campaign_type = t.campaign_type
