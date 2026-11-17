import { Area, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { C, dayLabel, dm, dmy, pct, vn } from '../format.js'
import { axis, grid, Guard, Sec, Table, Tile, Tip } from '../ui.jsx'

const METRIC = { orders: 'Đơn', gross_sales: 'Doanh thu lúc đặt', spend: 'Spend', cpo: 'CPO', mer: 'MER',
  new_share: 'Tỉ lệ khách mới', cancel_rate: 'Tỉ lệ huỷ', refunds: 'Tiền hoàn', email_orders: 'Đơn email' }
const LEVEL = { 'để ý': '▲ để ý', 'cần xử lý': '■ cần xử lý' }

export default function Alerts({ state }) {
  return (
    <Guard state={state}>{(d) => {
      const f = d.forecast
      // gộp đơn thật + dự báo vào 1 trục ngày; dải 80% vẽ bằng [lo, hi]
      const series = f ? [
        ...f.actual.map((a) => ({ date: a.date, actual: a.orders })),
        ...f.days.map((x) => ({ date: x.date, fc: x.fc, band: [x.lo, x.hi] })),
      ] : []
      return (<>
        <Sec title="Báo động 14 ngày gần nhất"
          cap={`${dm(d.since)} → ${dmy(d.until)}. So mỗi ngày với kỳ vọng (mức 7 ngày trước × hệ số thứ). ▲ để ý khi lệch ≥ 3,5 độ rộng; ■ cần xử lý khi ≥ 6 hoặc 2 ngày liền cùng chiều. Ngày có sự kiện (lễ, BFCM) thường báo vì chính sự kiện.`} />
        {d.alerts.length === 0 ? <div className="note">Không có báo động nào trong 14 ngày.</div> : (
          <Table rows={d.alerts} cols={[
            { key: 'date', label: 'Ngày', fmt: dayLabel }, { key: 'level', label: 'Mức', fmt: (v) => LEVEL[v] || v },
            { key: 'metric', label: 'Chỉ số', fmt: (v) => METRIC[v] || v }, { key: 'value', label: 'Thực tế', num: true, fmt: (v) => vn(v) },
            { key: 'expected', label: 'Kỳ vọng', num: true, fmt: (v) => vn(v) },
            { key: 'pct_vs_expected', label: 'Lệch', num: true, fmt: (v) => pct(v, 0, true) }, { key: 'event', label: 'Sự kiện', fmt: (v) => v || '' },
          ]} />)}
        <div className="cap" style={{ marginTop: 12 }}>Kiểm dữ liệu đã nạp đủ trước khi tin một cú "tụt". Hỏi chi tiết: "Hôm qua có gì lạ không?" trong Claude Code.</div>

        <Sec title="Dự báo đơn 14 ngày tới" cap="Đường xanh = đơn thật 28 ngày đã trọn; đường tím nét đứt = dự báo (ETS); dải = khoảng 80% từng ngày." />
        {!f ? <div className="note">{d.forecast_error || 'Chưa có dự báo được công bố.'}</div> : (<>
          <div className="note">Mốc dự báo: {dmy(f.origin)}. {f.stale ? 'DỰ BÁO CŨ: mốc khác ngày trọn của kho; đây không phải 14 ngày kế tiếp kể từ dữ liệu mới nhất.' : 'Đủ 14 ngày kể từ mốc.'}</div>
          <div className="tiles three">
            <Tile k="Tổng 14 ngày" v={`${vn(f.total, 0)} đơn`} d={`${dm(f.days[0].date)} → ${dm(f.days.at(-1).date)}`} />
            <Tile k="Khoảng 80% cho tổng" v={`${vn(f.range[0], 0)}–${vn(f.range[1], 0)}`} d={`± ${vn(f.p80_pct, 1)}% (sai số tổng 14 ngày khi kiểm lại quá khứ)`} />
            <Tile k="Trung bình mỗi ngày" v={`${vn(f.total / f.days.length, 0)} đơn`} d={`28 ngày qua: ${vn(f.actual_mean, 0)} đơn/ngày`} />
          </div>
          <div className="card" style={{ marginTop: 16 }}><ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={series} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
              <CartesianGrid {...grid} />
              <XAxis dataKey="date" tickFormatter={dm} {...axis} minTickGap={24} />
              <YAxis {...axis} width={40} />
              <Tooltip content={<Tip labelFmt={dayLabel} fmt={(v) => (Array.isArray(v) ? `${vn(v[0], 0)}–${vn(v[1], 0)}` : vn(v, 0))} />} />
              <Legend wrapperStyle={{ fontSize: 13 }} />
              <Area isAnimationActive={false} name="Khoảng 80%" dataKey="band" fill={C.spend} fillOpacity={0.15} stroke="none" />
              <Line isAnimationActive={false} name="Đơn thật" dataKey="actual" stroke={C.rev} strokeWidth={2} dot={false} />
              <Line isAnimationActive={false} name="Dự báo" dataKey="fc" stroke={C.spend} strokeWidth={2} strokeDasharray="6 4" dot={false} />
              <ReferenceLine x={d.until} stroke={C.muted} />
            </ComposedChart>
          </ResponsiveContainer></div>
          <details className="sql"><summary>Xem số dự báo và cận từng ngày</summary><Table rows={f.days} cols={[{key:'date',label:'Ngày',fmt:dayLabel},{key:'fc',label:'Dự báo',num:true,fmt:v=>vn(v,0)},{key:'lo',label:'Cận dưới 80%',num:true,fmt:v=>vn(v,0)},{key:'hi',label:'Cận trên 80%',num:true,fmt:v=>vn(v,0)}]}/></details>
          <div className="note"><b>Đọc dự báo:</b> không cộng cận dưới / trên của từng ngày để ra khoảng cho tổng (dùng ô "Khoảng 80% cho tổng").
            Mô hình chưa biết sự kiện: Thanksgiving, Black Friday có thể lệch xa dải. Kịch bản "nếu chi X USD/ngày" hỏi trong Claude Code.</div>
        </>)}
      </>)
    }}</Guard>
  )
}
