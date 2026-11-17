-- Kiểm bước B (hoàn tiền). Dán vào BigQuery Console, bôi đen 1 câu rồi Run.

-- 1. Tổng tiền hoàn: cộng từng lần hoàn (stg_refunds) phải bằng total_refunded ghi trên đơn.
select
  (select count(*) from silver.stg_refunds)                                           as so_lan_hoan,
  (select round(sum(refund_amount), 2) from silver.stg_refunds)                       as tong_hoan_theo_lan,
  (select round(sum(total_refunded), 2) from silver.stg_orders)                       as tong_hoan_tren_don,
  (select countif(total_refunded > 0) from silver.stg_orders)                         as so_don_co_hoan;

-- 2. Đơn nào lệch (nếu câu 1 không bằng nhau): tổng các lần hoàn khác total_refunded của đơn.
select o.order_id, o.order_name, o.total_refunded, round(sum(r.refund_amount), 2) as cong_cac_lan
from silver.stg_orders o
left join silver.stg_refunds r using (order_id)
where o.total_refunded > 0 or r.refund_id is not null
group by 1, 2, 3
having abs(coalesce(sum(r.refund_amount), 0) - o.total_refunded) > 0.01
order by 3 desc;

-- 3. Hoàn tiền theo tháng hoàn (giờ Phoenix).
select format_date('%Y-%m', refund_date) as thang, count(*) as so_lan, round(sum(refund_amount), 2) as tien_hoan
from silver.stg_refunds
group by 1 order by 1;
