-- Silver: 1 dòng = 1 message email, gộp 2 loại về một bảng:
--   campaign: gửi hàng loạt một lần (bảng campaign_messages, nối campaigns để lấy tên campaign)
--   flow:     email tự động (bỏ giỏ, chào mừng...) (bảng flow_messages, nối flows để lấy tên flow)
-- Dùng để biết message_id trong số đếm hằng ngày thuộc campaign hay flow nào.
select
    m.message_id,
    'campaign'                         as channel,
    m.campaign_id                      as parent_id,
    c.name                             as parent_name,
    m.name                             as message_name,
    m.status                           as status
from {{ source('raw', 'klaviyo_campaign_messages') }} m
left join {{ source('raw', 'klaviyo_campaigns') }} c on c.campaign_id = m.campaign_id

union all

select
    m.message_id,
    'flow'                             as channel,
    m.flow_id                          as parent_id,
    f.name                             as parent_name,
    m.name                             as message_name,
    f.status                           as status
from {{ source('raw', 'klaviyo_flow_messages') }} m
left join {{ source('raw', 'klaviyo_flows') }} f on f.flow_id = m.flow_id
