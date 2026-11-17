-- Mô hình 8, bất thường, bước 1: kiểm mart_anomaly_daily (sau dbt build).

-- Câu 1: TỈ LỆ BÁO ĐỘNG theo từng chỉ số. Nếu ngưỡng hợp lý thì "để ý" chỉ vài % số ngày,
-- "cần xử lý" hiếm (vài ngày cả giai đoạn). Chỉ số nào báo > 10% số ngày là ngưỡng/sàn nhiễu của nó đang quá hẹp.
select metric, any_value(method) as method,
       count(*)                                   as ngay,
       countif(level = 'để ý')                    as de_y,
       countif(level = 'cần xử lý')               as can_xu_ly,
       countif(level = '(không tính được)')       as khong_tinh,
       round(100 * countif(level in ('để ý', 'cần xử lý')) / count(*), 1) as pct_bao,
       min(date) as tu_ngay, max(date) as den_ngay
from gold.mart_anomaly_daily
group by metric
order by pct_bao desc;

-- Câu 2: GỘP CẢ 9 CHỈ SỐ: bao nhiêu % ngày có ít nhất 1 báo động (bài học: 9 chỉ số dễ thành ~40%).
select count(*) as ngay,
       countif(n_bao > 0)  as ngay_co_bao,
       round(100 * countif(n_bao > 0) / count(*), 1) as pct_ngay_co_bao,
       countif(n_xu_ly > 0) as ngay_can_xu_ly
from (
  select date, countif(level in ('để ý', 'cần xử lý')) as n_bao, countif(level = 'cần xử lý') as n_xu_ly
  from gold.mart_anomaly_daily group by date
);

-- Câu 3: MỌI báo động "cần xử lý", mới nhất trước. Đọc từng dòng và tự hỏi: ngày đó có chuyện thật không
-- (đổi ngân sách ads, sale, lễ, gửi campaign email, lỗi web)? Nhiều dòng không giải thích được = báo nhầm.
-- Đổi mức (như 10–27/10) giờ chỉ nên báo vài ngày đầu, không kéo dài cả tuần.
select date, weekday, metric, value, level_7d, weekday_factor, expected, pct_vs_expected, score, direction
from gold.mart_anomaly_daily
where level = 'cần xử lý'
order by date desc, abs(score) desc;

-- Câu 4: TÍNH TAY 1 ô (orders, ngày đã trọn mới nhất).
--   a) trung bình cột value của 7 dòng 'mức' = level_7d ở dòng 'ngày xét';
--   b) cột ratio của 8 dòng 'cùng thứ' (giá trị ÷ mức của chính ngày đó): trung vị 8 số = weekday_factor;
--   c) expected = level_7d × weekday_factor.
with d as (select max(date) as t from gold.mart_anomaly_daily where metric = 'orders')
select 'ngày xét' as vai, a.date, a.value, a.level_7d, a.weekday_factor, a.expected, a.mad_ratio, a.noise_floor,
       a.score, a.level, null as ratio
from gold.mart_anomaly_daily a, d where a.metric = 'orders' and a.date = d.t
union all
select 'mức', p.date, p.orders, null, null, null, null, null, null, null, null
from gold.daily_performance p, d where date_diff(d.t, p.date, day) between 1 and 7
union all
select 'cùng thứ', a.date, a.value, a.level_7d, null, null, null, null, null, null, round(a.value / a.level_7d, 4)
from gold.mart_anomaly_daily a, d
where a.metric = 'orders' and date_diff(d.t, a.date, day) between 7 and 56 and mod(date_diff(d.t, a.date, day), 7) = 0
order by vai desc, date desc;

-- Câu 5: TUẦN 10–16/9 (Long Sleeve tụt, CPO 14/9 gấp 2,4 lần ở bản cũ). Bản mới phải còn thấy ngày 14/9 lạ.
select date, weekday, metric, value, expected, pct_vs_expected, score, level
from gold.mart_anomaly_daily
where date between '2026-09-10' and '2026-09-16'
  and (metric in ('cpo', 'orders', 'spend', 'mer') or level != 'bình thường')
order by date, metric;
