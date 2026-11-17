-- Kiểm mart_cohort_clv hợp lý (lỗi thì chặn build). Có dòng ở đây = sai:
--   cộng dồn không được GIẢM theo tháng (tăng hoặc giữ nguyên); tháng 0 bội số = 1;
--   cỡ cohort khớp mart_cohort_retention; khoảng tin cậy bao lấy trung bình.
with c as (
  select *, lag(avg_cum_rev) over (partition by cohort_month order by month_offset) as prev
  from {{ ref('mart_cohort_clv') }}
)
select c.cohort_month, c.month_offset, c.avg_cum_rev, c.prev, c.multiple_of_first, c.cohort_size, r.cohort_size as r_size
from c
left join {{ ref('mart_cohort_retention') }} r using (cohort_month, month_offset)
where (c.prev is not null and c.avg_cum_rev < c.prev - 0.01)
   or (c.month_offset = 0 and c.first_month_rev > 0 and abs(c.multiple_of_first - 1) > 0.001)
   or r.cohort_size is null or r.cohort_size != c.cohort_size
   or c.ci_low > c.avg_cum_rev or c.ci_high < c.avg_cum_rev
