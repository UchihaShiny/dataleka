-- Tuần 3, bước 2 (tiếp): kết quả trước chỉ hiện 50 dòng đầu. 2 câu tổng hợp này ít dòng hơn.
-- Kiểu tên MỚI: bắt đầu bằng 'Catalog-' hoặc 'Static-' (ví dụ Catalog-PDP_Phone Case_Theme): phần 2 là product type.
-- Kiểu tên CŨ: 'Scale:CBO:Lowest Cost_Catalog_ULS ...', 'Test:ABO_Bear'...: phần 2 là chiến thuật/chủ đề, không phải type.

-- Câu 1: theo tháng, bao nhiêu % spend là kiểu tên mới.
select
  format_date('%Y-%m', date)                                              as thang,
  round(sum(spend), 2)                                                    as tong_spend,
  round(sum(if(regexp_contains(campaign_name, r'^(Catalog|Static)-'), spend, 0)), 2) as spend_kieu_moi,
  round(100 * safe_divide(
    sum(if(regexp_contains(campaign_name, r'^(Catalog|Static)-'), spend, 0)), sum(spend)), 1) as pct_kieu_moi
from gold.fct_ad_day
group by 1
order by 1;

-- Câu 2: chỉ kiểu tên mới, gom theo type (phần 2). Mong ít hơn 20 dòng.
select
  split(campaign_name, '_')[safe_offset(1)]   as type_doan,
  count(distinct campaign_name)               as so_campaign,
  min(date)                                   as ngay_dau,
  max(date)                                   as ngay_cuoi,
  round(sum(spend), 2)                        as tong_spend
from gold.fct_ad_day
where regexp_contains(campaign_name, r'^(Catalog|Static)-')
group by 1
having sum(spend) > 0
order by tong_spend desc;
