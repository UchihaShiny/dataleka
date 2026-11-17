-- 13/11: kiểm lịch sự kiện sau dbt build (seed events → dim_event → mart_anomaly_daily).

-- Câu 1: báo động vào NGÀY SỰ KIỆN (có cột event). Kỳ vọng thấy 11/11 Veterans Day gross_sales "để ý".
select date, weekday, event, metric, value, expected, pct_vs_expected, score, level
from gold.mart_anomaly_daily
where event is not null and level != 'bình thường'
order by date, metric;

-- Câu 2: tỉ lệ báo động sau khi bỏ ngày sự kiện khỏi mốc (trước: 11,5% số ngày, 6 ngày "cần xử lý").
select count(*) as ngay, countif(n_bao > 0) as ngay_co_bao, round(100 * countif(n_bao > 0) / count(*), 1) as pct,
       countif(n_xu_ly > 0) as ngay_can_xu_ly, countif(co_su_kien) as ngay_su_kien
from (
  select date, logical_or(event is not null) as co_su_kien,
         countif(level in ('để ý', 'cần xử lý')) as n_bao, countif(level = 'cần xử lý') as n_xu_ly
  from gold.mart_anomaly_daily group by date
);

-- Câu 3: tuần SAU Memorial Day (25/5), Labor Day (7/9): mức 7 ngày phải không tính ngày lễ.
-- Cột n_le_trong_7_ngay > 0 mà level_7d vẫn hợp lý (không bị kéo theo ngày lễ) là đúng.
select a.date, a.metric, a.value, a.level_7d, a.expected, a.level,
       (select count(*) from gold.dim_event e where e.date between date_sub(a.date, interval 7 day) and date_sub(a.date, interval 1 day)) as n_le_trong_7_ngay
from gold.mart_anomaly_daily a
where a.metric = 'orders' and a.date between '2026-09-06' and '2026-09-15'
order by a.date;

-- Câu 4 (13/11, sau câu 2: báo động 11,5% → 14,2%, 26 → 33 ngày): báo động mới đến từ đâu?
-- nhom = 'mốc thiếu' khi ngày được chấm bằng ít mốc hơn trước (nhân < 8 ngày cùng thứ, hiếm < 28 ngày) vì có
-- ngày sự kiện bị bỏ; 'sau sự kiện' khi trong 7 ngày trước có sự kiện; 'ngày sự kiện'; còn lại 'thường'.
with a as (
  select a.*,
    (select count(*) from gold.dim_event e
     where e.date between date_sub(a.date, interval 7 day) and date_sub(a.date, interval 1 day)) as le_7_ngay_truoc
  from gold.mart_anomaly_daily a
  where a.level in ('để ý', 'cần xử lý')
)
select
  case when event is not null then 'ngày sự kiện'
       when (method = 'nhân theo thứ' and n_base < 8) or (method = 'TB 28 ngày' and n_base < 28) then 'mốc thiếu'
       when le_7_ngay_truoc > 0 then 'sau sự kiện'
       else 'thường' end as nhom,
  date, weekday, metric, n_base, value, expected, pct_vs_expected, score, level
from a
order by nhom, date;
