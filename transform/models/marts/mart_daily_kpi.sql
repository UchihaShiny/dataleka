-- Gold (tuần 3): 1 dòng = 1 ngày kinh doanh (giờ Phoenix), đúng 7 chỉ số của brief:
-- Rev, Orders, AOV, Spend, MER, CPO, CM ước.
--
-- KHÔNG tính lại từ đầu: lấy rev, orders, spend, mer, cpo từ daily_performance, để mỗi chỉ số chỉ có
-- một chỗ định nghĩa. Ở đây chỉ thêm 2 chỉ số mới: AOV và CM ước.
--
--   aov    = rev / orders                                   (giá trị trung bình một đơn)
--   cm_est = rev × (1 − cogs_rate − fee_rate) − spend       (lợi nhuận góp ước tính, công thức brief)
--
-- cogs_rate (28%) và fee_rate (3,8%) đặt ở vars trong dbt_project.yml, không viết cứng ở đây.
-- Đây là tỉ lệ TẠM theo brief; khi có context/cogs.csv của anh Quang thì thay bằng giá vốn thật.
-- spend null (ngày chưa nạp Meta) thì mer, cpo, cm_est cũng null: không biết chi phí thì không biết lãi.
select
    date,
    rev,
    orders,
    round(safe_divide(rev, nullif(orders, 0)), 2)                                        as aov,
    spend,
    mer,
    cpo,
    round(rev * (1 - {{ var('cogs_rate') }} - {{ var('fee_rate') }}) - spend, 2)        as cm_est
from {{ ref('daily_performance') }}
