-- Gold (mô hình 2, RFM): 1 dòng = 1 khách, trạng thái TẠI NGÀY DỮ LIỆU MỚI NHẤT (as_of_date). Ảnh chụp, không phải lịch sử.
--
--   R recency_days = số ngày từ đơn cuối tới as_of_date          → r_band theo ngưỡng HÀNH VI (vars rfm_r_*), không ngũ phân vị
--   F frequency    = số đơn không huỷ                             → f_band cố định: 1 / 2 / 3+ (phần lớn khách chỉ mua 1 lần,
--                                                                    ngũ phân vị cho 4 mức cùng là "1 đơn", vô nghĩa)
--   M monetary     = tổng rev (current_total, đã trừ hoàn) đơn không huỷ → m_score ngũ phân vị 1–5 (5 = chi nhiều nhất)
--
-- Khác dim_customer ở 1 chỗ: CHỈ ĐẾM ĐƠN KHÔNG HUỶ. Khách đặt, huỷ, đặt lại chỉ là 1 lần mua thật; đếm cả huỷ thì bị xếp
-- nhầm vào "Mới quay lại". Khách chỉ có đơn huỷ không có trong bảng này.
-- Ngưỡng R mặc định 60 / 180 / 365 ngày (dbt_project.yml). Kiểm lại bằng checks/sql/da-kiem/check_rfm_b1.sql câu 1 (khoảng cách
-- đơn 1 → đơn 2 thực tế) và sửa vars nếu không khớp.
--
-- Thứ tự gán nhóm (luật trên thắng luật dưới):
--   1. R > 365                          → Đã mất
--   2. R gần mất (181–365), M = 5       → Không thể để mất   (chi nhiều nhất, đang bỏ đi)
--   3. R gần mất, F ≥ 2                 → Có nguy cơ         (từng tốt, đang bỏ đi: nhóm cần cứu nhất)
--   4. F ≥ 3, R còn nóng                → Champions
--   5. F ≥ 3, R đang nguội              → Loyal
--   6. F = 2, R còn nóng                → Mới quay lại
--   7. F = 2, R đang nguội              → Cần chú ý
--   8. F = 1, R còn nóng                → Khách mới           (luôn tách riêng, không so với khách cũ)
--   9. F = 1, R đang nguội hoặc gần mất → Ngủ đông
with orders as (
    select customer_key, order_date, rev
    from {{ ref('fct_orders') }}
    where customer_key is not null and not is_cancelled
),
as_of as (
    select max(order_date) as d from {{ ref('fct_orders') }}
),
per_customer as (
    select
        o.customer_key,
        max(o.order_date)                         as last_order_date,
        count(*)                                  as frequency,
        sum(o.rev)                                as monetary
    from orders o
    group by 1
),
scored as (
    select
        p.*,
        a.d                                                        as as_of_date,
        date_diff(a.d, p.last_order_date, day)                     as recency_days,
        ntile(5) over (order by p.monetary)                        as m_score
    from per_customer p
    cross join as_of a
),
banded as (
    select
        *,
        case
            when recency_days <= {{ var('rfm_r_hot') }}  then 'còn nóng'
            when recency_days <= {{ var('rfm_r_cool') }} then 'đang nguội'
            when recency_days <= {{ var('rfm_r_lost') }} then 'gần mất'
            else 'đã mất'
        end                                                        as r_band,
        case when frequency >= 3 then '3+' else cast(frequency as string) end as f_band
    from scored
)
select
    customer_key,
    as_of_date,
    last_order_date,
    recency_days,
    frequency,
    round(monetary, 2)                                             as monetary,
    r_band,
    f_band,
    m_score,
    case
        when r_band = 'đã mất'                          then 'Đã mất'
        when r_band = 'gần mất' and m_score = 5         then 'Không thể để mất'
        when r_band = 'gần mất' and frequency >= 2      then 'Có nguy cơ'
        when frequency >= 3 and r_band = 'còn nóng'     then 'Champions'
        when frequency >= 3                             then 'Loyal'
        when frequency = 2 and r_band = 'còn nóng'      then 'Mới quay lại'
        when frequency = 2                              then 'Cần chú ý'
        when r_band = 'còn nóng'                        then 'Khách mới'
        else 'Ngủ đông'
    end                                                            as segment
from banded
