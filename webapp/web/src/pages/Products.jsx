import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { C, dm, dmy, money, pct, short, vn } from '../format.js'
import { axis, EndLabel, grid, Guard, Sec, Table, Tile, Tip } from '../ui.jsx'

import Explorer from '../Explorer.jsx'

export default function Products({ state }) {
  return (
    <Guard state={state}>{(d, period) => {
      const sp = d.species.map((s) => ({ ...s, label: `${money(s.rev)}  ${pct(s.change_pct, 1, true)}` }))
      return (<>
        <Explorer title="Thiết kế & sản phẩm" rows={d.explore || []} nameKey="product_title" filterKey="product_line" truncated={d.truncated} cols={[
          {key:'product_title',label:'Thiết kế'},{key:'product_line',label:'Dòng'},
          {key:'revenue',label:'Doanh thu dòng (USD)',num:true,fmt:v=>money(v,2)},
          {key:'units',label:'Số cái còn lại',num:true,fmt:v=>vn(v,0)},
          {key:'returned',label:'Số cái hoàn',num:true,fmt:v=>vn(v,0)}]}/>
        <p className="cap">Theo ngày đặt trong kỳ chọn, cùng quy tắc fct_lines. Doanh thu dòng đã trừ hoàn sản phẩm, không gồm ship/thuế; không đồng nhất với Rev đơn hàng.</p>
        <Sec title="Top 10 species, kỳ chọn so kỳ trước"
          cap={`${dm(period.start)} → ${dm(period.end)} so với ${dm(period.p_start)} → ${dm(period.p_end)}. Loài đầu tiên trong tag species: của mẫu (không đếm trùng).`} />
        {!d.comparable&&<div className="note">Chưa đủ ngày ở hai kỳ; không tính % thay đổi species.</div>}
        <div className="chart-scroll"><div className="card wide-chart"><ResponsiveContainer width="100%" height={Math.max(200, 36 * sp.length)}>
          <BarChart data={sp} layout="vertical" margin={{ top: 8, right: 140, left: 8, bottom: 0 }}>
            <CartesianGrid stroke={C.line} horizontal={false} />
            <XAxis type="number" tickFormatter={short} {...axis} />
            <YAxis type="category" dataKey="species" width={110} interval={0} {...axis} />
            <Tooltip cursor={{ fill: C.surface2 }} content={<Tip fmt={(v, p) => `${money(v)} (${pct(p.payload.change_pct, 1, true)} so kỳ trước)`} />} />
            <Bar isAnimationActive={false} name="Kỳ này" dataKey="rev" fill={C.rev} maxBarSize={16} radius={[0, 4, 4, 0]}>
              <LabelList dataKey="label" content={EndLabel} />
            </Bar>
          </BarChart>
        </ResponsiveContainer></div></div>
        <details className="sql"><summary>Xem bảng số species</summary><Table rows={d.species} cols={[{key:'species',label:'Species'},{key:'rev',label:'Doanh thu dòng (USD)',num:true,fmt:v=>money(v,2)},{key:'change_pct',label:'So kỳ trước',num:true,fmt:v=>pct(v,1,true)}]}/></details>
        <div className="cap" style={{ marginTop: 12 }}><b>Bẫy:</b> {pct(d.species_none_pct, 0)} doanh thu kỳ này ({money(d.species_none_rev)}) là mẫu chưa gắn tag species (nhiều mẫu mới, Phone Case), nên bảng loài chưa phải toàn shop.</div>

        <Sec title="Hoàn trả theo dòng sản phẩm"
          cap={`Đơn đặt ${dm(period.start)} → ${dm(period.end)}. Kỳ này hoàn <b>${vn(d.returns.returned, 0)}</b> / ${vn(d.returns.sold, 0)} cái (<b>${pct(d.returns.pct, 2)}</b>), ${money(d.returns.value)}. Tính theo ngày ĐẶT, chỉ phần hoàn gắn với sản phẩm (không gồm hoàn ship, hoàn một phần tiền), nên nhỏ hơn ô Hoàn tiền ở Tổng quan (tính theo ngày hoàn). Đơn gần đây còn có thể bị hoàn thêm. <b>Tô đỏ</b>: % hoàn từ 1% trở lên (gấp khoảng 2 lần mức chung của shop; ngưỡng tạm, chưa chốt), số cái còn ít nên xem cả số cái.`} />
        {d.returns.lines.length ? <Table rows={d.returns.lines} cols={[
          { key: 'product_line', label: 'Dòng' }, { key: 'sold', label: 'Bán (cái)', num: true, fmt: (v) => vn(v, 0) },
          { key: 'returned', label: 'Hoàn (cái)', num: true, fmt: (v) => vn(v, 0) },
          { key: 'return_pct', label: '% hoàn', num: true, fmt: (v) => pct(v, 2), cls: (r) => (r.return_pct >= 1 ? 'lose' : '') },
          { key: 'returned_value', label: 'Tổng tiền hoàn', num: true, fmt: (v) => money(v, 2) },
          { key: 'avg', label: 'TB mỗi cái', num: true, fmt: (_, r) => (r.returned ? money(r.returned_value / r.returned, 2) : '–') },
        ]} /> : <div className="note">Kỳ này chưa có hoàn trả.</div>}
        {d.returns.top.length > 0 && <>
          <h4 className="rp-title">5 mẫu hoàn nhiều tiền nhất</h4>
          <Table rows={d.returns.top} cols={[
            { key: 'product_title', label: 'Mẫu' }, { key: 'product_line', label: 'Dòng' },
            { key: 'returned', label: 'Hoàn / bán', num: true, fmt: (v, r) => `${vn(v, 0)} / ${vn(r.sold, 0)}` },
            { key: 'return_pct', label: '% hoàn', num: true, fmt: (v) => pct(v, 1) },
            { key: 'returned_value', label: 'Tổng tiền hoàn', num: true, fmt: (v) => money(v, 2) },
            { key: 'avg', label: 'TB mỗi cái', num: true, fmt: (_, r) => (r.returned ? money(r.returned_value / r.returned, 2) : '–') },
          ]} />
        </>}

        {d.abc.window && <>
          <Sec title="Mẫu nào gánh doanh thu (ABC, cố định 90 ngày)"
            cap={`<b>Không theo bộ lọc ngày</b>: luôn 90 ngày ${dm(d.abc.window[0])} → ${dmy(d.abc.window[1])}, bỏ đơn huỷ. A = các mẫu làm ra 80% doanh thu đầu, B = 80→95%, C = còn lại có bán, D = đang mở bán nhưng 0 cái, Mới = dưới 30 ngày tuổi.`} />
          <div className="tiles five">{d.abc.groups.map((g) => (
            <Tile key={g.cls} k={`Nhóm ${g.cls}`} v={`${vn(g.mau, 0)} mẫu`} d={`<b>${pct(g.rev_pct)}</b> doanh thu · ${pct(g.mau_pct)} số mẫu`} />))}</div>
          <Table rows={d.abc.top.map((r, i) => ({ ...r, i: i + 1 }))} cols={[
            { key: 'i', label: '#', num: true }, { key: 'product_title', label: 'Mẫu' }, { key: 'product_line', label: 'Dòng' },
            { key: 'abc_class', label: 'Nhóm' }, { key: 'revenue', label: 'Doanh thu', num: true, fmt: (v) => vn(v) },
            { key: 'units', label: 'Số cái', num: true, fmt: (v) => vn(v, 0) }, { key: 'share_pct', label: '% tổng', num: true, fmt: (v) => pct(v) },
          ]} />
        </>}
      </>)
    }}</Guard>
  )
}
