// Thành phần dùng chung: ô KPI, tiêu đề mục, bảng, tooltip biểu đồ, khung chờ / lỗi.
import { Component } from 'react'
import { C } from './format.js'

export const Tile = ({ k, v, d, h }) => (
  <div className="tile">
    <div className="k">{k}</div>
    <div className="v">{v}</div>
    {d && <div className="d" dangerouslySetInnerHTML={{ __html: d }} />}
    {h && <div className="h">{h}</div>}
  </div>
)

export const Sec = ({ title, cap }) => (
  <>
    <h3 className="sec">{title}</h3>
    {cap && <div className="cap" dangerouslySetInnerHTML={{ __html: cap }} />}
  </>
)

// cols: [{ key, label, num?, fmt? }]
export const Table = ({ cols, rows }) => (
  <div className="tbl" tabIndex={0} role="region" aria-label="Bảng dữ liệu, cuộn ngang nếu cần">
    <table>
      <thead><tr>{cols.map((c) => <th key={c.key} className={c.num ? 'num' : ''}>{c.label}</th>)}</tr></thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>{cols.map((c) => (
            <td key={c.key} className={(c.num ? 'num ' : '') + (c.cls ? c.cls(r) : '')}>
              {c.fmt ? c.fmt(r[c.key], r) : r[c.key]}
            </td>))}</tr>
        ))}
      </tbody>
    </table>
  </div>
)

// Tooltip: label đã định dạng + từng dòng (tên, màu, giá trị định dạng). Chữ dùng màu chữ, không dùng màu dữ liệu.
export const Tip = ({ active, payload, label, labelFmt, fmt }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="tip">
      <div className="t">{labelFmt ? labelFmt(label, payload) : label}</div>
      {payload.filter((p) => p.value !== null && p.value !== undefined).map((p) => (
        <div className="r" key={p.dataKey + p.name}>
          <span className="sw" style={{ background: p.color || p.fill || C.rev }} />
          <span>{p.name}: <b>{fmt ? fmt(p.value, p) : p.value}</b></span>
        </div>
      ))}
    </div>
  )
}

// Nhãn cuối cột ngang, 1 dòng: LabelList mặc định ngắt chữ theo độ dài cột (cột ngắn thì nhãn xuống dòng)
export const EndLabel = ({ x, y, width, height, value }) => (
  <text x={x + width + 6} y={y + height / 2} dy={4} fill={C.ink} fontSize={12}>{value}</text>
)

// getter: đọc màu lúc vẽ (đổi nền sáng/tối thì trục, lưới đổi theo)
export const axis = { get stroke() { return C.line }, get tick() { return { fill: C.muted, fontSize: 12 } }, tickLine: false }
export const grid = { get stroke() { return C.line }, vertical: false }

// Bắt lỗi khi vẽ 1 trang: chỉ trang đó báo lỗi, không trắng cả app.
export class Boundary extends Component {
  constructor(props) { super(props); this.state = { error: null } }
  static getDerivedStateFromError(error) { return { error } }
  componentDidUpdate(prev) { if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null }) }
  render() {
    if (this.state.error) return <div className="note err">Trang này gặp lỗi khi vẽ: {String(this.state.error.message || this.state.error)}</div>
    return this.props.children
  }
}

export function Guard({ state, children }) {
  if (state.error) return <div className="note err" role="alert">Không tải được số: {state.error} <button className="btn ghost small" onClick={()=>window.dispatchEvent(new Event('datae-retry'))}>Thử lại</button></div>
  if (!state.data) return <div className="loading" role="status">Đang tải số…</div>
  return children(state.data, state.period)
}
