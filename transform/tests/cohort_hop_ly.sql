-- Kiểm bảng cohort hợp lý (lỗi thì chặn build). Có dòng ở đây = sai:
--   tháng 0 phải đúng 100% (mọi khách đều mua ở tháng đầu của mình);
--   khoảng tin cậy phải bao lấy con số giữa; số khách hoạt động không vượt cỡ cohort.
select cohort_month, month_offset, retention_pct, ci_low, ci_high, active_customers, cohort_size
from {{ ref('mart_cohort_retention') }}
where (month_offset = 0 and retention_pct != 100)
   or ci_low > retention_pct or ci_high < retention_pct
   or active_customers > cohort_size
