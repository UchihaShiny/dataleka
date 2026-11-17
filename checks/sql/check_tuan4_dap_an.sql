-- Tuần 4 B6: ĐÁP ÁN 5 câu mẫu của brief, viết tay từ gold. Huy Anh chạy từng câu trên BigQuery console, lưu kết quả;
-- B7 so câu trả lời của Claude (phiên mới) với các số này.
-- Quy ước chung (giống server datae và mô tả cột):
--   - ngày = ngày kinh doanh America/Phoenix; "ngày trọn cuối" d = gold.load_status.complete_through (theo lúc nạp
--     Shopify, 16/11). Trước đây đoán max(order_date) − 1: nạp ngay sau nửa đêm Phoenix thì mất trọn 1 ngày;
--   - tỉ số (MER, ROAS, tỉ lệ) tính từ TỔNG, không lấy trung bình tỉ số từng ngày;
--   - tuần = Chủ nhật → thứ Bảy (brief câu 4).

-- Câu 1. MER và CM ước 7 ngày qua theo ngày Phoenix (7 ngày trọn cuối, từng ngày + tổng).
with d as (select complete_through as ngay_tron from `datae-514203.gold.load_status`)
select cast(k.date as string) as ngay, k.rev, k.spend, k.mer, k.cm_est
from `datae-514203.gold.mart_daily_kpi` k, d
where k.date between date_sub(d.ngay_tron, interval 6 day) and d.ngay_tron
union all
select 'TONG 7 ngay', round(sum(k.rev), 2), round(sum(k.spend), 2),
       round(safe_divide(sum(k.rev), sum(k.spend)), 4), round(sum(k.cm_est), 2)
from `datae-514203.gold.mart_daily_kpi` k, d
where k.date between date_sub(d.ngay_tron, interval 6 day) and d.ngay_tron
order by ngay;

-- Câu 2. Top 10 species theo Rev 28 ngày, so với 28 ngày trước đó.
-- Rev theo species = line_revenue (sau giảm giá, trả hàng; chưa ship, thuế), species = loài đầu tiên của mẫu
-- (dim_product.species). Mẫu không có tag species → '(không có species)', vẫn hiện để thấy tỉ trọng.
with d as (select complete_through as ngay_tron from `datae-514203.gold.load_status`),
s as (
  select coalesce(p.species, '(không có species)') as species,
         sum(if(l.order_date between date_sub(d.ngay_tron, interval 27 day) and d.ngay_tron, l.line_revenue, 0)) as rev_28d,
         sum(if(l.order_date between date_sub(d.ngay_tron, interval 55 day) and date_sub(d.ngay_tron, interval 28 day),
                l.line_revenue, 0)) as rev_28d_truoc
  from `datae-514203.gold.fct_lines` l
  left join `datae-514203.gold.dim_product` p using (product_id)
  cross join d
  where l.order_date between date_sub(d.ngay_tron, interval 55 day) and d.ngay_tron
  group by 1
)
select species, round(rev_28d, 2) as rev_28d, round(rev_28d_truoc, 2) as rev_28d_truoc,
       round(100 * safe_divide(rev_28d - rev_28d_truoc, rev_28d_truoc), 1) as doi_pct
from s
order by rev_28d desc
limit 11;   -- 11 để vẫn thấy top 10 nếu '(không có species)' chen vào

-- Câu 3. Tỉ lệ khách mua lần 2 trong 60 ngày theo product type của đơn đầu (đã kiểm ở check_tuan4_b3.sql câu 1–2).
select first_type, countif(is_eligible) as khach_du_60_ngay, countif(repeat_60d) as mua_lan_2,
       round(100 * safe_divide(countif(repeat_60d), countif(is_eligible)), 1) as ti_le_pct
from `datae-514203.gold.mart_repeat_60d`
group by 1
having countif(is_eligible) > 0
order by khach_du_60_ngay desc;

-- Câu 4. ROAS theo product type tuần trước (Chủ nhật → thứ Bảy, tuần trọn gần nhất).
-- ROAS = rev Shopify (line_revenue) / spend Meta theo type đọc từ tên campaign. '(không theo type)' = spend campaign
-- tên kiểu cũ, không gán được type.
with d as (select complete_through as ngay_tron from `datae-514203.gold.load_status`),
w as (
  select if(extract(dayofweek from ngay_tron) = 7, ngay_tron, date_sub(date_trunc(ngay_tron, week(sunday)), interval 1 day)) as sat from d
)
select format_date('%F', date_sub(w.sat, interval 6 day)) as tu_ngay, format_date('%F', w.sat) as den_ngay,
       t.product_line, round(sum(t.rev), 2) as rev, round(sum(t.spend), 2) as spend,
       round(safe_divide(sum(t.rev), nullif(sum(t.spend), 0)), 2) as roas
from `datae-514203.gold.mart_type_day` t, w
where t.date between date_sub(w.sat, interval 6 day) and w.sat
group by 1, 2, 3
order by spend desc, rev desc;

-- Câu 5. Doanh thu email (Klaviyo attributed) so với tổng Rev theo tuần (Chủ nhật → thứ Bảy), 8 tuần trọn gần nhất.
-- Doanh thu email = placed_value của channel campaign + flow (Klaviyo tự nhận); '(không gán)' KHÔNG tính.
-- Rev = tổng current_total (daily_performance.rev). Hai số khác định nghĩa (Klaviyo gán theo cửa sổ của nó, giá trị
-- lúc đặt), nên tỉ lệ chỉ để thấy cỡ đóng góp, không cộng trừ với rev.
with d as (select complete_through as ngay_tron from `datae-514203.gold.load_status`),
w as (
  select if(extract(dayofweek from ngay_tron) = 7, ngay_tron, date_sub(date_trunc(ngay_tron, week(sunday)), interval 1 day)) as sat from d
),
rev as (
  select date_trunc(p.date, week(sunday)) as tuan, sum(p.rev) as rev
  from `datae-514203.gold.daily_performance` p, w
  where p.date between date_sub(w.sat, interval 55 day) and w.sat
  group by 1
),
email as (
  select date_trunc(e.date, week(sunday)) as tuan,
         sum(if(e.channel in ('campaign', 'flow'), e.placed_value, 0)) as email_rev,
         sum(if(e.channel = 'campaign', e.placed_value, 0)) as campaign_rev,
         sum(if(e.channel = 'flow', e.placed_value, 0)) as flow_rev
  from `datae-514203.gold.email_daily` e, w
  where e.date between date_sub(w.sat, interval 55 day) and w.sat
  group by 1
)
select format_date('%F', r.tuan) as tuan_bat_dau, round(r.rev, 2) as rev, round(coalesce(e.email_rev, 0), 2) as email_rev,
       round(coalesce(e.campaign_rev, 0), 2) as campaign_rev, round(coalesce(e.flow_rev, 0), 2) as flow_rev,
       round(100 * safe_divide(e.email_rev, r.rev), 1) as email_pct_rev
from rev r left join email e using (tuan)
order by tuan_bat_dau;
