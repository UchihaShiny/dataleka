-- Gold (mô hình 8, phần BẤT THƯỜNG): 1 dòng = 1 ngày đã trọn × 1 chỉ số. "Hôm qua có gì lạ không?"
-- Cách làm (bài học 4b "trung vị, MAD" + "so cùng thứ", mùa vụ kiểu NHÂN ở mục 2):
--   level_7d       = trung bình 7 ngày NGAY TRƯỚC (không tính hôm nay): mức hiện tại của shop.
--   ratio của 1 ngày = giá trị ÷ level_7d của chính ngày đó (ngày đó cao/thấp bao nhiêu lần so với mức lúc ấy).
--   weekday_factor = trung vị ratio của 8 ngày CÙNG THỨ trước đó (thứ Bảy thường bằng 0,8 lần mức chẳng hạn).
--   expected       = level_7d × weekday_factor.
--   Vì sao đổi (12/11, câu 3 check_anomaly_b1): bản cũ lấy trung vị 8 ngày cùng thứ làm mốc. Shop tăng mức rất nhanh
--   (27–29/4 từ ~6 lên ~40 đơn; 10–27/10 spend lên gấp đôi) nên mốc bám mức cũ suốt nhiều tuần, báo "cao" 3 tuần liền.
--   Bản này: đổi mức thì chỉ báo vài ngày đầu (tin mới thật), sau ~1 tuần level_7d bắt kịp.
--   độ rộng = level_7d × 1,4826 × MAD(ratio của 8 ngày đó), nhưng KHÔNG nhỏ hơn sàn nhiễu (noise_floor) của từng loại
--           chỉ số, để 8 tuần tình cờ đều nhau không làm độ rộng gần 0 rồi báo loạn:
--             count  (orders, email_orders) : √expected (nhiễu Poisson)
--             money  (gross_sales)          : expected ÷ √(đơn kỳ vọng)
--             ratio  (cpo, mer)             : expected ÷ √(đơn kỳ vọng)
--             share  (new_share, cancel_rate): √(p(1−p) ÷ đơn kỳ vọng), p tối thiểu 1 ÷ đơn kỳ vọng
--             refunds                       : 1 AOV kỳ vọng (1 đơn hoàn cỡ thường không phải chuyện lạ)
--             spend                         : anomaly_spend_floor × expected (spend là quyết định của shop)
--   score = (giá trị − expected) ÷ độ rộng. level: 'để ý' khi |score| ≥ anomaly_watch; 'cần xử lý' khi ≥ anomaly_act,
--           hoặc ≥ anomaly_watch HAI NGÀY LIÊN TIẾP cùng chiều (bài học 4d: giảm báo động giả).
--   Chỉ chấm ngày có đủ 7 ngày trước để tính level_7d (level_7d > 0) và đủ anomaly_base_weeks ngày cùng thứ có ratio.
--   CHỈ SỐ HIẾM (cancel_rate, refunds, email_orders; method = 'TB 28 ngày'): phần lớn ngày bằng 0 nên mức 7 ngày hay
--   bằng 0, ratio không chia được (lỗi 12/11: cancel_rate mất hẳn khỏi bảng, refunds còn 54 ngày, email 97 ngày).
--   Chuyện hiếm không có nhịp tuần đáng tin, nên: expected = trung bình 28 ngày ngay trước, độ rộng =
--   max(1,4826 × MAD 28 giá trị, sàn nhiễu); MAD của chuỗi toàn 0 bằng 0 nên sàn nhiễu (Poisson, nhị thức, 1 AOV) quyết.
-- 9 chỉ số (Huy Anh chọn 12/11). Doanh thu dùng total_price LÚC ĐẶT (gross_sales), không dùng rev, vì rev ngày cũ
-- tự giảm khi có hoàn; MER ở đây cũng tính từ gross_sales nên KHÁC mer của daily_performance một chút.
-- new_share = đơn đầu tiên của khách ÷ đơn (đơn không email không có is_first_order, nên tỉ lệ hơi thấp hơn thật,
-- nhưng đều mọi ngày nên vẫn so được).
-- Chỉ ngày ĐÃ TRỌN: trước ngày của đơn mới nhất đã nạp (hôm nay chưa trọn thì "tụt 60%" giả). Spend null ngoài khoảng
-- Meta đã nạp (chưa có dữ liệu, không phải 0) nên spend, cpo, mer của các ngày đó không có dòng.
-- LỊCH SỰ KIỆN (seed events, Huy Anh chốt 13/11): ngày sự kiện VẪN được chấm, cột event ghi tên sự kiện cạnh báo
-- động, nhưng KHÔNG làm mốc cho ngày khác: không vào level_7d, không vào hệ số thứ, không vào TB 28 ngày. Vì vậy
-- Black Friday không kéo cao mức của tuần sau. Vẫn đủ 8 ngày cùng thứ / 28 ngày THƯỜNG làm mốc: gặp ngày sự kiện
-- thì lùi xa thêm (tối đa 12 tuần / 42 ngày).
-- Bẫy: luôn kiểm bất thường DỮ LIỆU trước (check_raw, freshness, reconcile). Ngày sale riêng của shop, ngày gửi
-- campaign email chưa có trong lịch nên vẫn bị báo; Q4 chưa từng có ở quy mô này.
{%- set rare = "('cancel_rate', 'refunds', 'email_orders')" %}
with loaded as (
    -- ngày ĐÃ TRỌN cuối (macro complete_through: theo lúc nạp Shopify). Không dùng current_date lúc build (lỗi
    -- 12/11: build chiều VN đã sang ngày mới ở Phoenix nên 11/11 mới nạp tới 18h bị coi là trọn), cũng không
    -- "ngày mới nhất có đơn − 1" (lỗi 16/11: nạp 00:07 Phoenix, ngày mới chưa có đơn nên mất trọn 1 ngày).
    select {{ complete_through() }} as complete_through
),
gross as (
    select order_date as date, sum(total_price) as gross_sales
    from {{ ref('fct_orders') }}
    group by 1
),
daily as (
    select
        d.date,
        d.orders,
        coalesce(g.gross_sales, 0)                              as gross_sales,
        d.spend,
        d.cpo,
        safe_divide(coalesce(g.gross_sales, 0), nullif(d.spend, 0)) as mer,
        safe_divide(d.first_orders, nullif(d.orders, 0))        as new_share,
        safe_divide(d.cancelled_orders, nullif(d.orders, 0))    as cancel_rate,
        d.refunds,
        d.email_orders
    from {{ ref('daily_performance') }} d
    left join gross g using (date)
    cross join loaded
    where d.date >= date '{{ var("anomaly_start") }}'
      and d.date <= loaded.complete_through
),
long as (
    select d.date, m.metric, m.kind, m.value, e.event, e.event is not null as is_event
    from daily d
    left join {{ ref('events') }} e on e.date = d.date
    cross join unnest([
        struct('orders' as metric, 'count' as kind, cast(d.orders as float64) as value),
        struct('gross_sales', 'money',   cast(d.gross_sales as float64)),
        struct('spend',       'spend',   cast(d.spend as float64)),
        struct('cpo',         'ratio',   cast(d.cpo as float64)),
        struct('mer',         'ratio',   cast(d.mer as float64)),
        struct('new_share',   'share',   cast(d.new_share as float64)),
        struct('cancel_rate', 'share',   cast(d.cancel_rate as float64)),
        struct('refunds',     'refunds', cast(d.refunds as float64)),
        struct('email_orders','count',   cast(d.email_orders as float64))
    ]) m
    where m.value is not null
),
leveled as (
    -- mức 7 ngày ngay trước (theo lịch), BỎ ngày sự kiện. Điều kiện chấm GIỮ NGUYÊN như trước khi có lịch: đủ cả 7 ngày
    -- lịch có số (n_all = 7, kể cả ngày sự kiện); chỉ phần trung bình là bỏ ngày sự kiện.
    -- (13/11: bản đầu hạ ngưỡng còn 5 ngày / 6 tuần / 24 ngày, làm chấm thêm các ngày đầu 4–5/2026 lúc shop rất nhỏ,
    -- báo động tăng 11,5% → 14,2%. Bỏ hạ ngưỡng, thay bằng lùi xa hơn để vẫn đủ mốc.)
    select
        *,
        avg(if(is_event, null, value)) over w   as level_7d,
        count(value) over w                     as n_all
    from long
    window w as (partition by metric order by unix_date(date) range between 7 preceding and 1 preceding)
),
rated as (
    select *,
           -- ratio dùng làm MỐC cho ngày khác: ngày sự kiện không có ratio
           if(n_all = 7 and level_7d > 0 and not is_event, value / level_7d, null) as ratio
    from leveled
),
cand as (
    -- ứng viên mốc: nhân theo thứ = các ngày cùng thứ lùi tới 12 tuần; hiếm = các ngày lùi tới 42 ngày
    select t.date, t.metric, t.kind, t.value, t.event, t.level_7d,
           if(t.metric in {{ rare }}, 'TB 28 ngày', 'nhân theo thứ')            as method,
           if(t.metric in {{ rare }}, 1, 7)                                      as step,
           if(t.metric in {{ rare }}, {{ var('anomaly_rare_days') }}, {{ var('anomaly_base_weeks') }}) as need,
           b.date as b_date, b.is_event as b_event,
           if(t.metric in {{ rare }}, b.value, b.ratio)                          as b_x,
           date_diff(t.date, b.date, day)                                        as gap
    from rated t
    join rated b
      on b.metric = t.metric
     and (   (t.metric not in {{ rare }} and date_diff(t.date, b.date, day) between 7 and 84
              and mod(date_diff(t.date, b.date, day), 7) = 0)
          or (t.metric in {{ rare }} and date_diff(t.date, b.date, day) between 1 and 42))
    where t.metric in {{ rare }} or (t.n_all = 7 and t.level_7d > 0)
),
ranked as (
    -- đếm ngày THƯỜNG từ gần tới xa; giữ tới ngày thường thứ `need`, ngày sự kiện xen giữa thì bỏ qua và lùi thêm
    select *, countif(not b_event) over (partition by date, metric order by b_date desc
                                         rows between unbounded preceding and current row) as rn
    from cand
),
kept as (
    select * from ranked where rn < need or (rn = need and not b_event)
),
valid as (
    -- đủ `need` ngày thường có giá trị, và không hụt ngày nào trên lịch trong đoạn đã lùi (số dòng = số bước lịch)
    select date, metric
    from kept
    group by date, metric
    having countif(not b_event and b_x is not null) = any_value(need)
       and count(*) = div(max(gap), any_value(step))
),
pairs as (
    select k.date, k.metric, k.kind, k.method, k.value, k.event, k.level_7d, k.b_x as base_x
    from kept k
    join valid using (date, metric)
    where not k.b_event
),
with_med as (
    select *, percentile_cont(base_x, 0.5) over (partition by date, metric) as med_x
    from pairs
),
with_mad as (
    select *, percentile_cont(abs(base_x - med_x), 0.5) over (partition by date, metric) as mad_x
    from with_med
),
stats_raw as (
    select date, metric, any_value(kind) as kind, any_value(method) as method, any_value(value) as value,
           any_value(event) as event,
           any_value(level_7d) as level_7d, any_value(med_x) as med_x, any_value(mad_x) as mad_x,
           avg(base_x) as mean_x, count(*) as n_base
    from with_mad
    group by 1, 2
),
stats as (
    select
        *,
        if(method = 'nhân theo thứ', med_x, null)                        as weekday_factor,
        if(method = 'nhân theo thứ', mad_x, null)                        as mad_ratio,
        if(method = 'TB 28 ngày', mean_x, null)                          as level_28d,
        if(method = 'nhân theo thứ', level_7d * med_x, mean_x)           as expected,
        if(method = 'nhân theo thứ', level_7d * 1.4826 * mad_x, 1.4826 * mad_x) as spread
    from stats_raw
    where (method = 'nhân theo thứ' and n_base = {{ var('anomaly_base_weeks') }})
       or (method = 'TB 28 ngày' and n_base = {{ var('anomaly_rare_days') }})
),
basis as (
    -- đơn kỳ vọng và AOV kỳ vọng của cùng ngày, dùng cho sàn nhiễu
    select o.date, o.expected as exp_orders,
           safe_divide(g.expected, nullif(o.expected, 0)) as exp_aov
    from stats o
    left join stats g on g.date = o.date and g.metric = 'gross_sales'
    where o.metric = 'orders'
),
scored as (
    select
        s.*,
        case s.kind
            when 'count'   then sqrt(greatest(s.expected, 1))
            when 'money'   then safe_divide(s.expected, sqrt(greatest(b.exp_orders, 1)))
            when 'ratio'   then safe_divide(s.expected, sqrt(greatest(b.exp_orders, 1)))
            when 'share'   then sqrt(safe_divide(
                                    greatest(s.expected, safe_divide(1, greatest(b.exp_orders, 1)))
                                    * (1 - least(greatest(s.expected, safe_divide(1, greatest(b.exp_orders, 1))), 0.99)),
                                    greatest(b.exp_orders, 1)))
            when 'refunds' then b.exp_aov
            when 'spend'   then {{ var('anomaly_spend_floor') }} * s.expected
        end as noise_floor
    from stats s
    left join basis b using (date)
),
final as (
    select
        *,
        greatest(spread, coalesce(noise_floor, 0)) as scale
    from scored
),
flagged as (
    select
        *,
        safe_divide(value - expected, nullif(scale, 0))                         as score,
        lag(safe_divide(value - expected, nullif(scale, 0))) over (partition by metric order by date) as prev_score,
        lag(date) over (partition by metric order by date)                      as prev_date
    from final
)
select
    date,
    format_date('%a', date)                                       as weekday,
    event,
    metric,
    kind,
    method,
    round(value, 4)                                               as value,
    round(level_7d, 4)                                            as level_7d,
    round(level_28d, 4)                                           as level_28d,
    round(weekday_factor, 4)                                      as weekday_factor,
    round(expected, 4)                                            as expected,
    round(mad_ratio, 4)                                           as mad_ratio,
    round(noise_floor, 4)                                         as noise_floor,
    round(scale, 4)                                               as scale,
    round(score, 2)                                               as score,
    round(100 * safe_divide(value - expected, nullif(expected, 0)), 1) as pct_vs_expected,
    case when score > 0 then 'cao' when score < 0 then 'thấp' end  as direction,
    case
        when score is null                                        then '(không tính được)'
        when abs(score) >= {{ var('anomaly_act') }}               then 'cần xử lý'
        when abs(score) >= {{ var('anomaly_watch') }}
         and prev_date = date_sub(date, interval 1 day)
         and abs(prev_score) >= {{ var('anomaly_watch') }}
         and sign(prev_score) = sign(score)                       then 'cần xử lý'
        when abs(score) >= {{ var('anomaly_watch') }}             then 'để ý'
        else 'bình thường'
    end                                                           as level,
    n_base
from flagged
