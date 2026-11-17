-- Gold: 1 dòng, kho có số TRỌN tới ngày nào (giờ Phoenix). Dashboard, MCP, forecast, câu SQL kiểm đọc bảng này
-- thay cho tự đoán "ngày mới nhất − 1". Cách tính ở macro complete_through().
select
    {{ complete_through() }}                                          as complete_through,
    (select max(order_date) from {{ ref('fct_orders') }})              as latest_order_date,
    {{ "'lúc nạp'" if var('complete_through', none) else "'đoán từ dữ liệu'" }} as method,
    current_timestamp()                                                as built_at
