-- Mô hình 5 (Pareto / ABC): KIỂM ĐỊNH theo bài học.
--   Câu 1: thứ hạng có ổn định qua 2 kỳ không ("kiểm tra mẫu có ở cùng một nhóm qua nhiều kỳ không").
--   Câu 2: hệ số Gini của 2 kỳ (độ tập trung, theo dõi qua thời gian).
--
-- Kỳ 2 (K2) = cửa sổ của gold.mart_product_abc (90 ngày tới ngày dữ liệu mới nhất).
-- Kỳ 1 (K1) = 90 ngày ngay trước đó. ABC của K1 tính lại tại chỗ bằng ĐÚNG luật của mart_product_abc
-- (bỏ đơn huỷ, bỏ Tip / UpCart / Shipping Protection / Gift Card, mẫu đủ 30 ngày tuổi tại cuối K1, ngưỡng 80% / 95%).
-- LƯU Ý: luật và ngưỡng CHÉP từ mart_product_abc.sql và vars dbt_project.yml. Đổi ở đó thì đổi ở đây.
-- Giới hạn: không biết mẫu nào "đang mở bán" tại cuối K1 (Shopify chỉ cho trạng thái hiện tại), nên K1 chỉ xếp các mẫu
-- CÓ BÁN trong K1 (A/B/C), không có nhóm D của K1.

-- Câu 1: ma trận chuyển nhóm. Mỗi hàng = nhóm ở K1, cột = nhóm ở K2, ô = % mẫu của hàng đó.
-- Ổn định nếu: phần lớn A của K1 vẫn là A ở K2 (khoảng 60% trở lên); A rất hiếm khi rơi thẳng xuống D.
with k2 as (
  select any_value(window_start) as s2, any_value(as_of_date) as e2 from gold.mart_product_abc
),
k as (
  select date_sub(s2, interval 90 day) as s1, date_sub(s2, interval 1 day) as e1 from k2
),
lines1 as (
  select coalesce(cast(l.product_id as string), concat('(đã xoá) ', l.product_title)) as product_key,
         l.product_id, l.line_revenue
  from gold.fct_lines l join gold.fct_orders o using (order_id), k
  where l.order_date between k.s1 and k.e1
    and not o.is_cancelled
    and not regexp_contains(lower(coalesce(l.product_title, '')), r'^tip$|upcart|shipping protection|\bgift card\b')
),
sales1 as (
  select product_key, any_value(product_id) as product_id, sum(line_revenue) as revenue
  from lines1 group by 1
),
mature1 as (
  -- đủ 30 ngày tuổi tại cuối K1; mẫu đã xoá không biết ngày tạo thì coi là đủ tuổi (như mart)
  select s.product_key, s.revenue
  from sales1 s
  left join gold.dim_product p on cast(p.product_id as string) = s.product_key
  cross join k
  where p.created_at is null
     or date_diff(k.e1, date(p.created_at, 'America/Phoenix'), day) >= 30
),
abc1 as (
  select product_key,
    case
      when safe_divide(coalesce(sum(revenue) over (order by revenue desc, product_key
             rows between unbounded preceding and 1 preceding), 0), sum(revenue) over ()) < 0.80 then 'A'
      when safe_divide(coalesce(sum(revenue) over (order by revenue desc, product_key
             rows between unbounded preceding and 1 preceding), 0), sum(revenue) over ()) < 0.95 then 'B'
      else 'C'
    end as nhom_k1
  from mature1
  where revenue > 0
),
chuyen as (
  select a.nhom_k1, coalesce(m.abc_class, '(ẩn/xoá, 0 cái)') as nhom_k2
  from abc1 a left join gold.mart_product_abc m using (product_key)
)
select
  nhom_k1,
  count(*)                                                                as so_mau_k1,
  round(100 * countif(nhom_k2 = 'A') / count(*), 1)                       as sang_A,
  round(100 * countif(nhom_k2 = 'B') / count(*), 1)                       as sang_B,
  round(100 * countif(nhom_k2 = 'C') / count(*), 1)                       as sang_C,
  round(100 * countif(nhom_k2 = 'D') / count(*), 1)                       as sang_D,
  round(100 * countif(nhom_k2 = '(ẩn/xoá, 0 cái)') / count(*), 1)          as an_xoa
from chuyen
group by 1
order by 1;

-- Câu 2: hệ số Gini (0 = mọi mẫu bán đều, gần 1 = dồn vào vài mẫu). Bài học: POD thường từ 0,8 trở lên.
-- Tính 2 cách: (a) mẫu đủ tuổi CÓ BÁN, so được giữa 2 kỳ; (b) K2 tính cả mẫu D (0 cái), đúng tinh thần "tính cả đuôi chết".
-- Gini = 2 × Σ(i × x_i) / (n × Σx) − (n + 1) / n, với x xếp tăng dần, i = 1..n.
with k2 as (
  select any_value(window_start) as s2 from gold.mart_product_abc
),
k as (select date_sub(s2, interval 90 day) as s1, date_sub(s2, interval 1 day) as e1 from k2),
k1_rev as (
  select coalesce(cast(l.product_id as string), concat('(đã xoá) ', l.product_title)) as product_key,
         any_value(l.product_id) as product_id, sum(l.line_revenue) as revenue
  from gold.fct_lines l join gold.fct_orders o using (order_id), k
  where l.order_date between k.s1 and k.e1 and not o.is_cancelled
    and not regexp_contains(lower(coalesce(l.product_title, '')), r'^tip$|upcart|shipping protection|\bgift card\b')
  group by 1
),
k1 as (
  select r.revenue from k1_rev r
  left join gold.dim_product p on cast(p.product_id as string) = r.product_key
  cross join k
  where r.revenue > 0
    and (p.created_at is null or date_diff(k.e1, date(p.created_at, 'America/Phoenix'), day) >= 30)
),
sets as (
  select 'K1, mẫu đủ tuổi có bán' as tap, revenue from k1
  union all select 'K2, mẫu đủ tuổi có bán', revenue from gold.mart_product_abc where not is_new and units > 0
  union all select 'K2, mẫu đủ tuổi kể cả D', revenue from gold.mart_product_abc where not is_new
),
ord as (
  select tap, revenue, row_number() over (partition by tap order by revenue) as i, count(*) over (partition by tap) as n
  from sets
)
select tap, any_value(n) as so_mau,
       round(2 * sum(i * revenue) / (any_value(n) * sum(revenue)) - (any_value(n) + 1) / any_value(n), 3) as gini
from ord
group by 1
order by 1;
