-- Tuần 3, bước 1: kiểm mart_daily_kpi (Huy Anh chạy trên BigQuery console).

-- Câu 1: 7 ngày 1–7/11. Kỳ vọng: orders 815, rev 44.319,85 (đúng số tuần 1, 2), spend ~24.098.
-- MER và AOV của cả tuần tính từ TỔNG, không lấy trung bình cột mer/aov từng ngày.
select
  sum(orders)                                   as orders,
  round(sum(rev), 2)                            as rev,
  round(sum(spend), 2)                          as spend,
  round(sum(rev) / sum(orders), 2)              as aov_tuan,
  round(sum(rev) / sum(spend), 4)               as mer_tuan,
  round(sum(cm_est), 2)                         as cm_est_tuan
from gold.mart_daily_kpi
where date between '2026-11-01' and '2026-11-07';

-- Câu 2: từng ngày 1–11/11. Kỳ vọng: cột rev, orders, spend, mer, cpo giống hệt daily_performance;
-- cm_est = rev × 0,682 − spend (tự bấm máy tính kiểm 1 dòng).
select k.*, round(k.rev * 0.682 - k.spend, 2) as cm_tu_tinh
from gold.mart_daily_kpi k
where date between '2026-11-01' and '2026-11-11'
order by date;

-- Câu 3: so với daily_performance mọi ngày. Kỳ vọng: 0 dòng (không lệch ngày nào).
select k.date
from gold.mart_daily_kpi k
join gold.daily_performance d using (date)
where k.rev != d.rev or k.orders != d.orders
   or coalesce(k.spend, -1) != coalesce(d.spend, -1);
