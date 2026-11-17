-- 13/11: dbt build có WARN mới "ad_type_chua_gan" = 2 dòng: campaign tên kiểu mới (Catalog-/Static-) có spend
-- nhưng type chưa có trong seeds/campaign_types.csv. Câu này cho biết là type nào, để thêm 1 dòng vào seed.
select campaign_type, campaign_name, min(date) as ngay_dau, max(date) as ngay_cuoi, round(sum(spend), 2) as tong_spend
from gold.fct_ad_day
where ad_product_line = '(chưa gán)'
group by 1, 2
having sum(spend) > 0
order by tong_spend desc;

-- Câu 2: "Youth Hoodie" thuộc product_line nào trong dim_product? (Shopify có thể xếp vào 'Hoodie' hoặc 1 dòng riêng)
select product_line, product_subline, count(*) as so_mau, countif(is_live) as dang_ban,
       any_value(title) as vi_du
from gold.dim_product
where lower(title) like '%youth%'
group by 1, 2
order by so_mau desc;
