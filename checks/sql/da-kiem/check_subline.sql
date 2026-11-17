-- Kiểm dòng con (sau dbt build --full-refresh). Dán vào BigQuery Console, bôi đen 1 câu rồi Run.

-- 1. Số tổng KHÔNG ĐỔI. Đúng (1–7/11): units 1338, line_revenue 41214.26; Long Sleeve 539 cái, Phone Case 337 cái.
select product_line, sum(units) as units, round(sum(line_revenue), 2) as line_revenue
from gold.product_daily where date between '2026-11-01' and '2026-11-07'
group by rollup(product_line) order by units desc;

-- 2. Dòng con trong 3 nhóm lớn có nhiều loại.
select product_line, product_subline, sum(units) as units, round(sum(line_revenue), 2) as doanh_thu,
       round(100 * sum(units) / sum(sum(units)) over (partition by product_line), 1) as pct_trong_nhom
from gold.product_daily
where date between '2026-11-01' and '2026-11-07' and product_line in ('Long Sleeve', 'Short Sleeve', 'Ornament')
group by 1, 2 order by 1, 3 desc;

-- 3. Mỗi dòng con lấy từ đâu (brief / suy từ tên / bằng nhóm lớn).
select product_subline_source, count(*) as san_pham from gold.dim_product group by 1 order by 2 desc;
