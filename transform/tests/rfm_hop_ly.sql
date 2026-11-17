-- Kiểm mart_rfm hợp lý (lỗi thì chặn build). Có dòng ở đây = sai:
--   F ≥ 1 (bảng chỉ có khách có ít nhất 1 đơn không huỷ); R không âm;
--   "Khách mới" phải đúng F = 1 và R còn nóng; Champions phải F ≥ 3 và R còn nóng.
select customer_key, frequency, recency_days, r_band, segment
from {{ ref('mart_rfm') }}
where frequency < 1
   or recency_days < 0
   or (segment = 'Khách mới' and not (frequency = 1 and r_band = 'còn nóng'))
   or (segment = 'Champions' and not (frequency >= 3 and r_band = 'còn nóng'))
