-- Kiểm silver + gold vòng 2. Dán vào BigQuery Console, bôi đen TỪNG câu rồi Run.
-- Mỗi câu ghi sẵn kết quả đúng. Số đã biết (1–7/11): 815 đơn, rev 44.319,85, line_revenue 41.214,26, spend 24.098,56.

-- 1. Bảng tổng dựng lại từ fact phải ra ĐÚNG số cũ (không được đổi số khi đổi cách dựng).
--    Đúng: don 815, rev 44319.85, spend 24098.56, line_revenue 41214.26
select
  (select sum(orders) from gold.daily_performance where date between '2026-11-01' and '2026-11-07')            as don,
  (select round(sum(rev), 2) from gold.daily_performance where date between '2026-11-01' and '2026-11-07')     as rev,
  (select round(sum(spend), 2) from gold.daily_performance where date between '2026-11-01' and '2026-11-07')   as spend,
  (select round(sum(line_revenue), 2) from gold.product_daily where date between '2026-11-01' and '2026-11-07') as line_revenue;

-- 2. Fact khớp nhau và khớp silver.
--    Đúng: 3 cặp số bằng nhau từng đôi.
select
  (select count(*) from gold.fct_orders)                                              as don_fact,
  (select countif(not is_test) from silver.stg_orders)                                as don_silver,
  (select count(*) from gold.fct_lines)                                               as dong_fact,
  (select count(*) from silver.stg_line_items l join silver.stg_orders o using (order_id) where not o.is_test) as dong_silver,
  (select round(sum(spend), 2) from gold.fct_ad_day)                                  as spend_fact,
  (select round(sum(spend), 2) from silver.stg_meta_ad_day)                           as spend_silver;

-- 3. Khách hàng: số khách, khách quay lại, LTV.
--    Đúng: tong_ltv = rev_don_co_email (cùng một tiền, nhìn theo khách); so_khach gần số dòng pii.shopify_customers.
select
  count(*)                                                as so_khach,
  countif(is_repeat)                                      as khach_quay_lai,
  round(100 * countif(is_repeat) / count(*), 1)           as pct_quay_lai,
  round(sum(ltv), 2)                                      as tong_ltv,
  (select round(sum(rev), 2) from gold.fct_orders where customer_key is not null) as rev_don_co_email,
  round(avg(ltv), 2)                                      as ltv_trung_binh
from gold.dim_customer;

-- 4. Đơn đầu tiên: mỗi khách đúng 1 đơn is_first_order.
--    Đúng: 2 số bằng nhau.
select
  (select countif(is_first_order) from gold.fct_orders)   as don_dau_tien,
  (select count(*) from gold.dim_customer)                as so_khach;

-- 5. Thuộc tính từ tag: bao nhiêu sản phẩm đọc được species, theme.
select product_line, count(*) as san_pham, countif(species is not null) as co_species,
       countif(theme is not null) as co_theme, countif(artist is not null) as co_artist
from gold.dim_product group by 1 order by 2 desc;

-- 6. Email: tổng Placed Order mọi kênh 1–7/11 phải bằng số reconcile Klaviyo đã khớp; phần gán cho email là bao nhiêu.
select channel, sum(received) as nhan, sum(opened) as mo, sum(clicked) as click,
       sum(placed_orders) as don, round(sum(placed_value), 2) as tien,
       round(100 * safe_divide(sum(opened), sum(received)), 1) as pct_mo
from gold.email_daily
where date between '2026-11-01' and '2026-11-07'
group by 1 order by don desc;

-- 7. Meta: ad đã xoá (không có trong cây ad) và phễu 1–7/11.
select
  countif(not in_ad_tree)                   as dong_ad_da_xoa,
  round(sum(spend), 2)                      as spend,
  sum(meta_view_content)                    as xem_sp,
  sum(meta_add_to_cart)                     as them_gio,
  sum(meta_initiate_checkout)               as thanh_toan,
  sum(meta_purchases)                       as mua_meta_tu_nhan
from gold.fct_ad_day
where date between '2026-11-01' and '2026-11-07';
