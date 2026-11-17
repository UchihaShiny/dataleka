-- Tuần 3, bước 2 (trước khi viết seed): xem MỌI tên campaign có spend trong kho, để biết shop đặt tên thế nào.
-- Quy ước đoán từ mẫu 1 ngày: <Format>-<Đích>_<Type>_<Audience>, ví dụ Catalog-PDP_Phone Case_Theme.
-- Cột type_doan = phần thứ 2 khi cắt tên theo dấu '_' (cái mình định dùng để tra product type).
-- Cột tổng đặt tên tong_spend, KHÔNG đặt 'spend': trùng tên cột gốc thì BigQuery hiểu having sum(spend)
-- là sum(sum(spend)) và báo 'Aggregations of aggregations are not allowed'.
-- Huy Anh chạy, copy hết kết quả gửi lại (khoảng vài chục dòng).
select
  split(campaign_name, '_')[safe_offset(1)]   as type_doan,
  campaign_name,
  min(date)                                   as ngay_dau,
  max(date)                                   as ngay_cuoi,
  round(sum(spend), 2)                        as tong_spend
from gold.fct_ad_day
group by 1, 2
having sum(spend) > 0
order by type_doan, tong_spend desc;
