-- Kiểm mart_repeat_60d hợp lý (lỗi thì chặn build). Có dòng ở đây = sai:
--   đơn 2 phải SAU ngày đơn đầu (khác ngày); repeat_60d null đúng khi chưa đủ 60 ngày;
--   repeat_60d = true thì days_to_second 1–60; khách khớp mart_rfm (cùng tập: khách có đơn không huỷ).
select 'don_2_cung_ngay' as loi, customer_key
from {{ ref('mart_repeat_60d') }}
where days_to_second is not null and days_to_second < 1
union all
select 'eligible_lech', customer_key
from {{ ref('mart_repeat_60d') }}
where (is_eligible and repeat_60d is null) or (not is_eligible and repeat_60d is not null)
union all
select 'repeat_sai', customer_key
from {{ ref('mart_repeat_60d') }}
where repeat_60d and not (days_to_second between 1 and 60)
union all
select 'lech_rfm', coalesce(a.customer_key, b.customer_key)
from {{ ref('mart_repeat_60d') }} a
full join {{ ref('mart_rfm') }} b using (customer_key)
where a.customer_key is null or b.customer_key is null
