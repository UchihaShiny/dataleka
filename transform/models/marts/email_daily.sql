-- Gold: 1 dòng = 1 ngày (Phoenix) × 1 message email. Số Klaviyo tự đếm.
-- channel: 'campaign' (gửi hàng loạt), 'flow' (tự động), '(không gán)' = Placed Order không gán cho email nào
-- (message_id '(none)': phần lớn đơn của shop), '(không rõ)' = message không tìm thấy trong danh sách.
-- placed_* là Klaviyo tự nhận (gán đơn cho email), chỉ để so trong kênh email; đơn thật lấy ở fct_orders.
-- Tỉ lệ mở/click phải tính từ tổng (sum opened / sum received), không lấy trung bình các dòng.
select
    d.date,
    d.message_id,
    case
        when not d.is_attributed then '(không gán)'
        else coalesce(m.channel, '(không rõ)')
    end                                                         as channel,
    m.parent_id,
    m.parent_name,                                              -- tên campaign hoặc tên flow
    m.message_name,
    sum(if(d.metric = 'received', d.count, 0))                  as received,
    sum(if(d.metric = 'opened', d.count, 0))                    as opened,
    sum(if(d.metric = 'clicked', d.count, 0))                   as clicked,
    sum(if(d.metric = 'placed_order', d.count, 0))              as placed_orders,
    sum(if(d.metric = 'placed_order', coalesce(d.value, 0), 0)) as placed_value
from {{ ref('stg_klaviyo_message_daily') }} d
left join {{ ref('stg_klaviyo_messages') }} m on m.message_id = d.message_id
group by 1, 2, 3, 4, 5, 6
