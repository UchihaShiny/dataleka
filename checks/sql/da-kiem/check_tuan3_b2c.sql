-- Tuần 3, bước 2: kiểm cột ad_product_line trong fct_ad_day (sau khi dbt build).

-- Câu 1: không mất spend. Kỳ vọng: tong_fct = tong_daily (cùng 1–10/11), chenh = 0.
select
  (select round(sum(spend), 2) from gold.fct_ad_day where date between '2026-11-01' and '2026-11-10')        as tong_fct,
  (select round(sum(spend), 2) from gold.daily_performance where date between '2026-11-01' and '2026-11-10') as tong_daily,
  round((select sum(spend) from gold.fct_ad_day where date between '2026-11-01' and '2026-11-10')
      - (select sum(spend) from gold.daily_performance where date between '2026-11-01' and '2026-11-10'), 2) as chenh;

-- Câu 2: spend theo type, 4–10/11 (7 ngày đã đóng). Kỳ vọng: '(chưa gán)' không có;
-- '(không theo type)' rất nhỏ (~0,3% spend tháng 11 là tên kiểu cũ).
select
  ad_product_line,
  round(sum(spend), 2)                                                as tong_spend,
  round(100 * sum(spend) / sum(sum(spend)) over (), 1)                as pct
from gold.fct_ad_day
where date between '2026-11-04' and '2026-11-10'
group by 1
order by tong_spend desc;

-- Câu 3: theo tháng, % spend có type. Kỳ vọng giống câu kiểu-mới trước: 0% tới 8/2026, ~50% 9, ~99% 10–11.
select
  format_date('%Y-%m', date)                                                       as thang,
  round(sum(spend), 2)                                                             as tong_spend,
  round(100 * safe_divide(sum(if(ad_product_line != '(không theo type)', spend, 0)), sum(spend)), 1) as pct_co_type
from gold.fct_ad_day
group by 1
order by 1;
