-- Mô hình 3 (CLV), bước 1: kiểm mart_cohort_clv (sau dbt build).

-- Câu 1: cohort nào đủ lớn và đủ tuổi để đọc CLV. Cột thang_xa_nhat_tron = tháng k lớn nhất đã kết thúc.
-- Mong đợi: cohort trước 2026 rất nhỏ; cohort lớn (từ 4/2026) mới có khoảng 6 tháng trọn.
select cohort_month, any_value(cohort_size) as so_khach,
       max(if(is_complete, month_offset, null)) as thang_xa_nhat_tron
from gold.mart_cohort_clv
group by 1
order by 1;

-- Câu 2: CLV lịch sử cohort 4–9/2026 ở tháng 0, 1, 3, 5 (trung bình / trung vị / bội số so với tháng 0).
-- Đọc: bội số tăng chậm = khách ít quay lại; trung vị gần tháng 0 = khách điển hình chỉ mua 1 lần. Dấu * = tháng chưa trọn.
select
  cohort_month,
  any_value(cohort_size) as so_khach,
  max(if(month_offset = 0, format('%.2f / %.2f', avg_cum_rev, median_cum_rev), null))                                as thang_0,
  max(if(month_offset = 1, format('%.2f / %.2f / x%.2f%s', avg_cum_rev, median_cum_rev, multiple_of_first, if(is_complete, '', ' *')), null)) as thang_1,
  max(if(month_offset = 3, format('%.2f / %.2f / x%.2f%s', avg_cum_rev, median_cum_rev, multiple_of_first, if(is_complete, '', ' *')), null)) as thang_3,
  max(if(month_offset = 5, format('%.2f (%.2f–%.2f) / x%.2f%s', avg_cum_rev, ci_low, ci_high, multiple_of_first, if(is_complete, '', ' *')), null)) as thang_5
from gold.mart_cohort_clv
where cohort_month between '2026-04' and '2026-09'
group by 1
order by 1;

-- Câu 3: khớp nguồn. Cộng doanh thu mọi cohort ở tháng cuối mỗi cohort = tổng rev các đơn có email. Kỳ vọng chenh = 0.
with cuoi as (
  select cohort_month, max(month_offset) as mo from gold.mart_cohort_clv group by 1
)
select
  round(sum(c.avg_cum_rev * c.cohort_size), 2)                                                 as tong_clv,
  (select round(sum(rev), 2) from gold.fct_orders where customer_key is not null)              as tong_rev_co_email,
  round(sum(c.avg_cum_rev * c.cohort_size)
      - (select sum(rev) from gold.fct_orders where customer_key is not null), 2)              as chenh
from gold.mart_cohort_clv c
join cuoi on cuoi.cohort_month = c.cohort_month and cuoi.mo = c.month_offset;
