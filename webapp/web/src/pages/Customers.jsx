import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { C, dm, dmy, money, pct, short, toDate, vn, weekRange } from '../format.js'
import { axis, grid, Guard, Sec, Table, Tip } from '../ui.jsx'

// màu ô cohort: nhạt (gần nền) → đậm theo %, chữ luôn màu chữ
function cellColor(v, max) {
  if (v === null || v === undefined) return C.surface
  const t = Math.min(1, v / (max || 1))
  const idx = Math.min(C.seq.length - 1, Math.floor(t * (C.seq.length - 1) + 0.5))
  return C.seq[idx]
}

function Cohort({ rows }) {
  if (!rows.length) return null
  const months = [...new Set(rows.map((r) => r.cohort_month))].sort().reverse()
  const ks = [...new Set(rows.map((r) => r.month_offset))].sort((a, b) => a - b)
  const max = Math.max(...rows.map((r) => r.retention_pct || 0))
  const at = (m, k) => rows.find((r) => r.cohort_month === m && r.month_offset === k)
  return (
    <div className="tbl"><table>
      <thead><tr><th>Cohort (số khách)</th>{ks.map((k) => <th key={k} className="num">Tháng {k}</th>)}</tr></thead>
      <tbody>{months.map((m) => {
        const size = rows.find((r) => r.cohort_month === m).cohort_size
        return (<tr key={m}><td>{m} ({vn(size, 0)})</td>{ks.map((k) => {
          const c = at(m, k)
          const bg = cellColor(c?.retention_pct, max)
          // ô xanh đậm (2 bậc cuối) thì chữ tối ở cả 2 nền: chữ sáng trên xanh chỉ ~2,8:1
          const dark = bg === C.seq[2] || bg === C.seq[3]
          return <td key={k} className="num" style={{ background: bg, color: bg === '#34755f' ? '#fffefa' : dark ? '#0A0F1E' : C.ink, fontWeight: dark ? 600 : 400 }}>
            {c ? `${pct(c.retention_pct)}${c.is_complete ? '' : '*'}` : ''}</td>
        })}</tr>)
      })}</tbody>
    </table></div>
  )
}

export default function Customers({ state }) {
  return (
    <Guard state={state}>{(d) => {
      const rt = d.repeat
      const repeatRows = rt.total ? [{ first_type: 'Cả shop', ...rt.total }, ...rt.rows] : []
      const cutoff = rt.as_of ? new Date(toDate(rt.as_of).getTime() - 60 * 86400000) : null
      return (<>
        <Sec title="Đơn theo loại khách, 12 tuần trọn"
          cap={`${dm(d.weeks[0])} → ${dmy(d.weeks[1])}. Khách mới = đơn đầu tiên của email đó; khách cũ = đơn thứ 2 trở đi; không email = đơn không có email (không biết mới hay cũ). 12 tuần: khách cũ chiếm <b>${pct(d.returning_pct)}</b> đơn có email.`} />
        <div className="card"><ResponsiveContainer width="100%" height={260}>
          <BarChart data={d.orders_weekly} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
            <CartesianGrid {...grid} />
            <XAxis dataKey="tuan" tickFormatter={weekRange} minTickGap={14} {...axis} />
            <YAxis {...axis} width={40} />
            <Tooltip cursor={{ fill: C.surface2 }} content={<Tip labelFmt={(l) => `Tuần ${weekRange(l)}`} fmt={(v) => `${vn(v, 0)} đơn`} />} />
            <Legend wrapperStyle={{ fontSize: 13 }} />
            <Bar isAnimationActive={false} name="Khách mới" dataKey="khach_moi" stackId="a" fill={C.cat[0]} stroke={C.surface} maxBarSize={24} />
            <Bar isAnimationActive={false} name="Khách cũ" dataKey="khach_cu" stackId="a" fill={C.cat[1]} stroke={C.surface} maxBarSize={24} />
            <Bar isAnimationActive={false} name="Không email" dataKey="khong_email" stackId="a" fill={C.other} stroke={C.surface} maxBarSize={24} />
          </BarChart>
        </ResponsiveContainer></div>

        <details className="sql"><summary>Xem bảng số khách theo tuần</summary><Table rows={d.orders_weekly} cols={[{key:'tuan',label:'Tuần',fmt:weekRange},{key:'khach_moi',label:'Đơn khách mới',num:true,fmt:v=>vn(v,0)},{key:'khach_cu',label:'Đơn khách cũ',num:true,fmt:v=>vn(v,0)},{key:'khong_email',label:'Không email',num:true,fmt:v=>vn(v,0)}]}/></details>
        <div className="grid2">
          <div>
            <Sec title="Mua lần 2 trong 60 ngày, theo type đơn đầu"
              cap={`Chỉ khách có đơn đầu đã đủ 60 ngày${cutoff ? ` (đơn đầu tới ${cutoff.toLocaleDateString('vi-VN')})` : ''}; bỏ đơn huỷ và đơn thêm cùng ngày. Type mới chưa có khách đủ 60 ngày.`} />
            <Table rows={repeatRows} cols={[
              { key: 'first_type', label: 'Type đơn đầu' }, { key: 'khach', label: 'Khách đủ 60 ngày', num: true, fmt: (v) => vn(v, 0) },
              { key: 'mua_lan_2', label: 'Mua lần 2', num: true, fmt: (v) => vn(v, 0) },
              { key: 'tile', label: 'Tỉ lệ', num: true, fmt: (_, r) => `${pct(100 * r.mua_lan_2 / r.khach)}${r.khach < 100 && r.first_type !== 'Cả shop' ? ' (mẫu nhỏ)' : ''}` },
            ]} />
          </div>
          <div>
            <Sec title="9 nhóm khách (RFM)" cap={`Ảnh chụp tại ${d.rfm_as_of || 'chưa biết'}; có thể gồm ngày đang dở theo thiết kế RFM. Chỉ đơn không huỷ. Doanh thu = tổng đã mua của nhóm.`} />
            <Table rows={d.rfm} cols={[
              { key: 'segment', label: 'Nhóm' }, { key: 'khach', label: 'Khách', num: true, fmt: (v) => vn(v, 0) },
              { key: 'khach_pct', label: '% khách', num: true, fmt: (v) => pct(v) }, { key: 'rev_pct', label: '% doanh thu', num: true, fmt: (v) => pct(v) },
            ]} />
          </div>
        </div>

        <Sec title="Giữ khách theo cohort (12 tháng gần nhất)" cap="Mỗi hàng = tháng mua đơn đầu. Ô = % khách của cohort có đơn trong tháng thứ k. Dấu * là tháng đang chạy, số còn tăng." />
        <Cohort rows={d.cohort} />

        <Sec title="CLV doanh thu lịch sử" cap="Doanh thu cộng dồn / khách của cohort từ tháng 0 đến tháng k. Đây là số đã xảy ra, chưa trừ giá vốn; không phải dự báo giá trị trọn đời. Giữ nguyên quy tắc cohort (kể cả đơn huỷ). Tháng * chưa hoàn tất; cohort < 100 khách có mẫu nhỏ."/>
        <Table rows={d.clv || []} cols={[{key:'cohort_month',label:'Cohort'},{key:'month_offset',label:'Tháng k',num:true,fmt:(v,r)=>`${v}${r.is_complete?'':'*'}`},{key:'cohort_size',label:'Khách',num:true,fmt:v=>`${vn(v,0)}${v<100?' · mẫu nhỏ':''}`},{key:'avg_cum_rev',label:'TB cộng dồn / khách',num:true,fmt:v=>money(v,2)},{key:'median_cum_rev',label:'Trung vị',num:true,fmt:v=>money(v,2)},{key:'ci_low',label:'Khoảng 95% của TB',fmt:(v,r)=>`${money(v,2)} – ${money(r.ci_high,2)}`}]} />

        <details className="sql"><summary>Xem bảng số email theo tuần</summary><Table rows={d.email_weekly} cols={[{key:'tuan',label:'Tuần',fmt:weekRange},{key:'campaign',label:'Campaign (USD)',num:true,fmt:v=>money(v,2)},{key:'flow',label:'Flow (USD)',num:true,fmt:v=>money(v,2)},{key:'rev',label:'Rev đơn hàng (USD)',num:true,fmt:v=>money(v,2)},{key:'email_pct',label:'Email % Rev',num:true,fmt:v=>pct(v)}]}/></details>
        <Sec title="Doanh thu email so với Rev, 12 tuần trọn" cap="Email = Placed Order Klaviyo gán cho campaign hoặc flow; đây là doanh thu được gán, không đo doanh thu gia tăng do email. Rev = tổng current_total (gồm ship, thuế)." />
        <div className="grid2">
          <div className="card"><ResponsiveContainer width="100%" height={240}>
            <BarChart data={d.email_weekly} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
              <CartesianGrid {...grid} />
              <XAxis dataKey="tuan" tickFormatter={weekRange} minTickGap={14} {...axis} />
              <YAxis tickFormatter={short} {...axis} width={44} />
              <Tooltip cursor={{ fill: C.surface2 }} content={<Tip labelFmt={(l) => `Tuần ${weekRange(l)}`} fmt={(v) => money(v)} />} />
              <Legend wrapperStyle={{ fontSize: 13 }} />
              <Bar isAnimationActive={false} name="Campaign" dataKey="campaign" stackId="e" fill={C.cat[2]} stroke={C.surface} maxBarSize={24} />
              <Bar isAnimationActive={false} name="Flow" dataKey="flow" stackId="e" fill={C.cat[0]} stroke={C.surface} maxBarSize={24} />
            </BarChart>
          </ResponsiveContainer></div>
          <div className="card"><ResponsiveContainer width="100%" height={240}>
            <LineChart data={d.email_weekly} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
              <CartesianGrid {...grid} />
              <XAxis dataKey="tuan" tickFormatter={weekRange} minTickGap={14} {...axis} />
              <YAxis tickFormatter={(v) => `${vn(v, 0)}%`} {...axis} width={44} />
              <Tooltip content={<Tip labelFmt={(l) => `Tuần ${weekRange(l)}`} fmt={(v) => pct(v)} />} />
              <Line isAnimationActive={false} name="Email % Rev" dataKey="email_pct" stroke={C.rev} strokeWidth={2} dot={{ r: 3, fill: C.rev }} />
            </LineChart>
          </ResponsiveContainer></div>
        </div>
      </>)
    }}</Guard>
  )
}
