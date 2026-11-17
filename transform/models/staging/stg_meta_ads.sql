-- Silver: 1 dòng = 1 ad Meta (cây ad: ad → adset → campaign, kèm creative).
-- effective_status là trạng thái LÚC NẠP (hôm nay), không phải trạng thái của từng ngày trong insights.
-- Ad đã xoá không có ở đây (Meta không trả qua /ads) nhưng số liệu cũ vẫn nằm trong insights:
-- nên mọi phép nối từ insights sang bảng này phải là LEFT JOIN.
select
    ad_id,
    ad_account_id,
    ad_name,
    adset_id,
    adset_name,
    campaign_id,
    campaign_name,
    campaign_objective,
    creative_id,
    effective_status                                         as effective_status_now,
    -- created_time có thể là TIMESTAMP hoặc chuỗi dạng 2026-01-01T00:00:00-0700: đọc được cả hai
    coalesce(safe_cast(created_time as timestamp),
             safe.parse_timestamp('%Y-%m-%dT%H:%M:%S%z', cast(created_time as string)))   as created_time
from {{ source('raw', 'meta_ads') }}
