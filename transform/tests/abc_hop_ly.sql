-- Kiểm mart_product_abc hợp lý (lỗi thì chặn build). Có dòng ở đây = sai:
--   D phải là 0 cái; A/B/C phải có bán; Mới phải dưới abc_new_days ngày tuổi;
--   trong mỗi nhóm tuổi: cum_share_pct tăng dần theo rank và mẫu cuối = 100 (± làm tròn);
--   A đứng trước B, B trước C theo thứ hạng của mẫu đủ tuổi (không có A nằm sau một B).
with t as (
  select *, lag(cum_share_pct) over (partition by is_new order by rank_all) as prev_cum,
         max(rank_all) over (partition by is_new) as last_rank
  from {{ ref('mart_product_abc') }}
)
select product_key, rank_all, abc_class, units, age_days, cum_share_pct
from t
where (abc_class = 'D' and units != 0)
   or (abc_class in ('A', 'B', 'C') and units = 0)
   or (abc_class = 'Mới' and age_days >= {{ var('abc_new_days') }})
   or (prev_cum is not null and cum_share_pct < prev_cum - 0.01)
   or (rank_all = last_rank and abs(cum_share_pct - 100) > 0.01 and cum_share_pct > 0)
   or (abc_class = 'A' and rank_all > (select min(rank_all) from {{ ref('mart_product_abc') }} where abc_class = 'B'))
   or (abc_class = 'B' and rank_all > (select min(rank_all) from {{ ref('mart_product_abc') }} where abc_class = 'C'))
   or (abc_class = 'Mới') != is_new
