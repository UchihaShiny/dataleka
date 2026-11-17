-- Mô hình 1 (Cohort), bước 1: kiểm mart_cohort_retention (sau dbt build).

-- Câu 1: cỡ cohort khớp dim_customer (cũng là số customer_summary đã trả). Kỳ vọng: 0 dòng.
select k.cohort_month, k.cohort_size, d.so_khach
from (select distinct cohort_month, cohort_size from gold.mart_cohort_retention) k
full outer join (select cohort_month, count(*) as so_khach from gold.dim_customer group by 1) d using (cohort_month)
where k.cohort_size is distinct from d.so_khach;

-- Câu 2: bảng tam giác 6/2026 → 10/2026, tháng thứ 0–4 (đọc theo hàng: rơi rụng; theo cột: so cohort).
-- Ô is_complete = false là tháng đang chạy, chưa so được.
select
  cohort_month,
  any_value(cohort_size)                                                      as so_khach,
  max(if(month_offset = 1, format('%.1f%% (%.1f–%.1f)%s', retention_pct, ci_low, ci_high, if(is_complete, '', ' *')), null)) as thang_1,
  max(if(month_offset = 2, format('%.1f%% (%.1f–%.1f)%s', retention_pct, ci_low, ci_high, if(is_complete, '', ' *')), null)) as thang_2,
  max(if(month_offset = 3, format('%.1f%% (%.1f–%.1f)%s', retention_pct, ci_low, ci_high, if(is_complete, '', ' *')), null)) as thang_3,
  max(if(month_offset = 4, format('%.1f%% (%.1f–%.1f)%s', retention_pct, ci_low, ci_high, if(is_complete, '', ' *')), null)) as thang_4
from gold.mart_cohort_retention
where cohort_month between '2026-06' and '2026-10'
group by cohort_month
order by cohort_month;
