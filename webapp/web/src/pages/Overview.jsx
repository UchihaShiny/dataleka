import OverviewBrief from './OverviewBrief.jsx'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { C, dayLabel, dm, money, pct, short, vn } from '../format.js'
import { axis, grid, Guard, Sec, Table, Tile, Tip } from '../ui.jsx'

function delta(change, comparable, key, upGood) {
  if (!comparable) return 'so kỳ trước: kỳ trước thiếu ngày, không so'
  const p = change[key]
  if (p === null || p === undefined) return 'so kỳ trước: –'
  const arrow = p > 0 ? '▲' : p < 0 ? '▼' : '■'
  const word = upGood === null || p === 0 ? '' : (p > 0) === upGood ? ' tốt hơn' : ' kém hơn'
  return `${arrow} <b>${vn(Math.abs(p), 1)}%</b> so kỳ trước${word}`
}

export default function Overview({ state, meta }) {
  return (
    <Guard state={state}>{(d, period) => {
      const t = d.totals, be = meta?.breakeven ?? 1.47, rf = d.refunds
      const tiles = [
        ['Doanh thu', money(t.rev), 'rev', true, 'Shopify current_total, đã trừ hoàn'],
        ['Đơn', vn(t.orders, 0), 'orders', true, 'Kể cả đơn huỷ'],
        ['AOV', money(t.aov, 2), 'aov', true, 'Rev ÷ đơn'],
        ['Spend', money(t.spend), 'spend', null, 'Meta, mọi tài khoản'],
        ['MER', vn(t.mer), 'mer', true, `Rev ÷ spend, từ tổng · hoà vốn ${vn(be)}`],
        ['CPO', money(t.cpo, 2), 'cpo', false, 'Spend ÷ đơn'],
        ['CM ước', money(t.cm_est), 'cm_est', true, `Giá vốn tạm ${vn(d.cogs_rate * 100, 0)}% + phí ${vn(d.fee_rate * 100, 1)}%`],
      ]
      const days = d.days
      return (<>
        <OverviewBrief data={d} period={period} />
        <div className="cap">{dm(period.start)} → {dm(period.end)} ({t.days} ngày), so với {dm(period.p_start)} → {dm(period.p_end)} ({d.previous.days} ngày)</div>
        {t.days !== d.expected_days && <div className="note err">Chỉ có {t.days}/{d.expected_days} ngày. Tổng kỳ chưa biết; không so kỳ trước. Ngày thiếu để trống, không thay bằng 0.</div>}
        <div className="tiles">
          {tiles.map(([k, v, key, up, h]) => <Tile key={k} k={k} v={v} h={h} d={delta(d.change, d.comparable, key, up)} />)}
          <Tile k="Hoàn tiền" v={money(rf.amount)} h={`${vn(rf.orders, 0)} đơn có lần hoàn đầu tiên trong kỳ · ${pct(rf.pct_of_rev)} rev · theo ngày hoàn`}
            d={delta({ refunds: rf.change }, d.comparable, 'refunds', false)} />
        </div>
        <div className="grid2">
          <div>
            <Sec title="Rev và spend theo ngày" cap="USD. Rev: Shopify, spend: Meta." />
            <div className="card"><ResponsiveContainer width="100%" height={260}>
              <LineChart data={days} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
                <CartesianGrid {...grid} />
                <XAxis dataKey="date" tickFormatter={dm} {...axis} />
                <YAxis tickFormatter={short} {...axis} width={48} />
                <Tooltip content={<Tip labelFmt={dayLabel} fmt={(v) => money(v)} />} />
                <Legend wrapperStyle={{ color: C.ink, fontSize: 13 }} />
                <Line isAnimationActive={false} name="Rev" dataKey="rev" stroke={C.rev} strokeWidth={2} dot={false} activeDot={{ r: 5, stroke: C.surface, strokeWidth: 2 }} />
                <Line isAnimationActive={false} name="Spend" dataKey="spend" stroke={C.spend} strokeWidth={2} dot={false} activeDot={{ r: 5, stroke: C.surface, strokeWidth: 2 }} />
              </LineChart>
            </ResponsiveContainer></div>
          </div>
          <div>
            <Sec title="MER theo ngày" cap={`Dưới đường hoà vốn ${vn(be)} thì CM ước âm.`} />
            <div className="card"><ResponsiveContainer width="100%" height={260}>
              <LineChart data={days} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
                <CartesianGrid {...grid} />
                <XAxis dataKey="date" tickFormatter={dm} {...axis} />
                <YAxis domain={['auto', 'auto']} tickFormatter={(v) => vn(v, 1)} {...axis} width={40} />
                <Tooltip content={<Tip labelFmt={dayLabel} fmt={(v) => vn(v)} />} />
                <ReferenceLine y={be} stroke={C.muted} label={{ value: `hoà vốn ${vn(be)}`, fill: C.muted, fontSize: 12, position: 'insideBottomLeft' }} />
                <Line isAnimationActive={false} name="MER" dataKey="mer" stroke={C.rev} strokeWidth={2} dot={false} activeDot={{ r: 5, stroke: C.surface, strokeWidth: 2 }} />
              </LineChart>
            </ResponsiveContainer></div>
          </div>
        </div>
        <Sec title="CM ước theo ngày" cap="USD. Cột dưới vạch 0 là ngày lỗ (theo giá vốn tạm)." />
        <div className="card"><ResponsiveContainer width="100%" height={220}>
          <BarChart data={days} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
            <CartesianGrid {...grid} />
            <XAxis dataKey="date" tickFormatter={dm} {...axis} />
            <YAxis tickFormatter={short} {...axis} width={48} />
            <Tooltip cursor={{ fill: C.surface2 }} content={<Tip labelFmt={dayLabel} fmt={(v) => money(v)} />} />
            <ReferenceLine y={0} stroke={C.muted} />
            <Bar isAnimationActive={false} name="CM ước" dataKey="cm_est" fill={C.rev} maxBarSize={24} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer></div>
        <div className="quick-links"><a href={`#ads?preset=${new URLSearchParams(window.location.hash.split('?')[1]).get('preset')||'7'}`} >Khám phá hiệu quả quảng cáo ↗</a><a href={`#products?preset=${new URLSearchParams(window.location.hash.split('?')[1]).get('preset')||'7'}`} >Xem sản phẩm ↗</a><a href="#trust">Hiểu công thức chỉ số ↗</a></div>
        <Sec title="Số từng ngày" cap="Bảng số tương ứng với các biểu đồ ở trên, hỗ trợ đọc bằng bàn phím và đối chiếu từng ngày." />
        <Table rows={days} cols={[
          { key: 'date', label: 'Ngày', fmt: dayLabel }, { key: 'rev', label: 'Rev', num: true, fmt: (v) => vn(v) },
          { key: 'orders', label: 'Đơn', num: true, fmt: (v) => vn(v, 0) }, { key: 'spend', label: 'Spend', num: true, fmt: (v) => vn(v) },
          { key: 'mer', label: 'MER', num: true, fmt: (v) => vn(v) }, { key: 'cpo', label: 'CPO', num: true, fmt: (v) => vn(v) },
          { key: 'cm_est', label: 'CM ước', num: true, fmt: (v) => vn(v), cls: (r) => (r.cm_est < 0 ? 'lose' : '') },
        ]} />
        <div className="note"><b>Cách đọc.</b> Chỉ tính ngày đã trọn theo giờ Phoenix (lúc nạp); ngày đang dở không tính.
          MER, AOV, CPO tính từ tổng của kỳ, không lấy trung bình từng ngày. <b>CM ước chưa phải lãi ròng:</b> giá vốn tạm, chờ cogs.csv.
          Định nghĩa từng chỉ số: transform/metrics.yml.</div>
      </>)
    }}</Guard>
  )
}
