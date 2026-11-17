-- Cảnh báo (không chặn build): campaign tên kiểu mới có spend nhưng type chưa có trong seeds/campaign_types.csv.
-- Có dòng ở đây = đội ads mở type mới (ví dụ 'Trucker Cap'): thêm 1 dòng vào seed rồi dbt build.
{{ config(severity='warn') }}
select campaign_type, campaign_name, round(sum(spend), 2) as tong_spend
from {{ ref('fct_ad_day') }}
where ad_product_line = '(chưa gán)'
group by 1, 2
having sum(spend) > 0
