// Vẽ 1 báo cáo từ spec (bar | line | table) + gọi API báo cáo. Dùng chung cho trang Hỏi Claude (xem trước)
// và Báo cáo của tôi.
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { C, dm, short, vn } from './format.js'
import { axis, grid, Table, Tip } from './ui.jsx'

export async function api(url, opts = {}) {
  const r = await fetch(url, opts.body ? { signal: AbortSignal.timeout(45000), method: 'POST', headers: { 'Content-Type': 'application/json' }, ...opts, body: JSON.stringify(opts.body) } : { signal: AbortSignal.timeout(45000), ...opts })
  const body = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(body.detail || body.error || `Lỗi ${r.status}`)
  return body
}

const isDay = (v) => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v)
const label = (v) => (isDay(v) ? dm(v) : v)
const num = (v) => (typeof v === 'number' ? vn(v, Number.isInteger(v) ? 0 : 2) : v)

export function ReportChart({ spec, data }) {
  if (!data.rows.length) return <div className="note">Câu SQL chạy được nhưng không có dòng nào.</div>
  if (spec.chart === 'table') {
    const cols = data.columns.map((k) => ({ key: k, label: k, num: typeof data.rows[0][k] === 'number', fmt: num }))
    return <>{data.truncated&&<p className="note">Kết quả bị giới hạn ở 500 dòng; đây không phải toàn bộ dữ liệu.</p>}<Table cols={cols} rows={data.rows} /></>
  }
  const many = data.rows.length > 16
  const common = (<>
    <CartesianGrid {...grid} />
    <XAxis dataKey={spec.x} tickFormatter={label} minTickGap={14} {...axis} />
    <YAxis tickFormatter={short} {...axis} width={52} />
    <Tooltip cursor={{ fill: C.surface2 }} content={<Tip labelFmt={(l) => label(l)} fmt={num} />} />
    {spec.y.length > 1 && <Legend wrapperStyle={{ fontSize: 13 }} />}
  </>)
  return (
    <>{data.truncated&&<p className="note">Kết quả bị giới hạn ở 500 dòng; biểu đồ chỉ biểu diễn các dòng trả về.</p>}<details className="sql"><summary>Xem bảng số biểu đồ</summary><Table rows={data.rows} cols={data.columns.map(k=>({key:k,label:k,num:typeof data.rows[0][k]==='number',fmt:num}))}/></details><div className="card"><ResponsiveContainer width="100%" height={320}>
      {spec.chart === 'line'
        ? <LineChart data={data.rows} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
            {common}
            {spec.y.map((k, i) => <Line isAnimationActive={false} key={k} dataKey={k} stroke={C.cat[i % C.cat.length]} strokeWidth={2} dot={!many} />)}
          </LineChart>
        : <BarChart data={data.rows} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
            {common}
            {spec.y.map((k, i) => <Bar isAnimationActive={false} key={k} dataKey={k} fill={C.cat[i % C.cat.length]} stackId={spec.stack ? 'a' : undefined}
              stroke={C.surface} strokeWidth={spec.stack ? 1 : 0} maxBarSize={28} />)}
          </BarChart>}
    </ResponsiveContainer></div></>
  )
}
