-- Tuần 3, bước 3: kiểm mart_type_day (sau dbt build).

-- Câu 1: cộng lại khớp nguồn, 4–10/11. Kỳ vọng:
--   spend_type = spend_kpi (= 23.696,91), chenh_spend = 0;
--   rev_type = line_revenue của product_daily cùng khoảng (chenh_rev = 0); rev_type < rev_kpi (thiếu ship, thuế).
select
  (select round(sum(spend), 2) from gold.mart_type_day  where date between '2026-11-04' and '2026-11-10') as spend_type,
  (select round(sum(spend), 2) from gold.mart_daily_kpi where date between '2026-11-04' and '2026-11-10') as spend_kpi,
  round((select sum(spend) from gold.mart_type_day  where date between '2026-11-04' and '2026-11-10')
      - (select sum(spend) from gold.mart_daily_kpi where date between '2026-11-04' and '2026-11-10'), 2) as chenh_spend,
  (select round(sum(rev), 2) from gold.mart_type_day  where date between '2026-11-04' and '2026-11-10') as rev_type,
  round((select sum(rev) from gold.mart_type_day where date between '2026-11-04' and '2026-11-10')
      - (select sum(line_revenue) from gold.product_daily where date between '2026-11-04' and '2026-11-10'), 2) as chenh_rev,
  (select round(sum(rev), 2) from gold.mart_daily_kpi where date between '2026-11-04' and '2026-11-10') as rev_kpi;

-- Câu 2: ROAS theo type cả tuần 4–10/11, tính từ TỔNG (không lấy trung bình roas từng ngày).
-- Đây là bảng sẽ đem demo: type nào tiêu nhiều mà ROAS thấp.
select
  product_line,
  round(sum(rev), 2)                               as rev,
  round(sum(spend), 2)                             as spend,
  round(safe_divide(sum(rev), sum(spend)), 2)      as roas_tuan
from gold.mart_type_day
where date between '2026-11-04' and '2026-11-10'
group by 1
order by spend desc, rev desc;
