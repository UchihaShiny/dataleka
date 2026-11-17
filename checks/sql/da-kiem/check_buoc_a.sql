-- Kiểm bước A (theo sản phẩm). Dán từng câu vào BigQuery Console, bôi đen 1 câu rồi Run.

-- 1. Doanh thu dòng sản phẩm 1–7/11 so với tiền của đơn.
--    line_revenue phải NHỎ HƠN rev (rev còn ship, thuế) và GẦN subtotal (tiền hàng sau giảm giá).
select
  (select sum(units) from gold.product_daily where date between '2026-11-01' and '2026-11-07')        as units_gold,
  (select sum(l.quantity) from raw.shopify_order_line_items l
     join silver.stg_orders o using (order_id)
     where o.order_date between '2026-11-01' and '2026-11-07' and not o.is_test)                      as units_raw,
  (select round(sum(line_revenue), 2) from gold.product_daily
     where date between '2026-11-01' and '2026-11-07')                                                 as line_revenue,
  (select round(sum(cast(subtotal as numeric)), 2) from raw.shopify_orders r
     join silver.stg_orders o using (order_id)
     where o.order_date between '2026-11-01' and '2026-11-07' and not o.is_test)                      as subtotal_don,
  -- line_revenue (sau trả hàng) phải gần bằng current_subtotal (subtotal sau trả hàng)
  (select round(sum(cast(current_subtotal as numeric)), 2) from raw.shopify_orders r
     join silver.stg_orders o using (order_id)
     where o.order_date between '2026-11-01' and '2026-11-07' and not o.is_test)                      as current_subtotal_don,
  (select round(sum(rev), 2) from gold.daily_performance
     where date between '2026-11-01' and '2026-11-07')                                                 as rev;

-- 2. Doanh thu theo dòng sản phẩm 1–7/11.
select product_line, sum(orders) as don, sum(units) as so_luong, round(sum(line_revenue), 2) as doanh_thu
from gold.product_daily
where date between '2026-11-01' and '2026-11-07'
group by 1 order by doanh_thu desc;

-- 3. Tiền tố SKU khớp với productType nào (để chốt bảng ánh xạ với anh Quang).
select sku_prefix, product_type, count(*) as san_pham
from gold.dim_product
group by 1, 2 order by 1, 3 desc;
