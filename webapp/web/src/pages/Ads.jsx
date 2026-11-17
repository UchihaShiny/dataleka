import { Bar, BarChart, CartesianGrid, Cell, LabelList, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { C, money, pct, vn } from '../format.js'
import { axis, EndLabel, Guard, Sec, Table, Tile, Tip } from '../ui.jsx'

import Explorer from '../Explorer.jsx'

const CAP = 6   // trục ROAS chặn ở 6: type spend gần 0 có ROAS hàng trăm làm cột khác thành vạch

export default function Ads({ state, meta }) {
  return (
    <Guard state={state}>{(d) => {
      const be = meta?.breakeven ?? 1.47
      const cap = Math.max(CAP, be * 1.5)
      const typed = d.types.filter((t) => t.roas !== null && t.product_line !== '(không theo type)')
        .sort((a, b) => b.spend - a.spend)
        .map((t) => ({ ...t, plot: Math.min(t.roas, cap),
          label: `${vn(t.roas)}${t.status === 'đang lỗ' ? '  ▼ đang lỗ' : ''}${t.roas > cap ? '  (vượt trục)' : ''}` }))
      return (<>
        <Sec title="ROAS theo product type"
          cap={`Rev Shopify của type (chưa ship, thuế) ÷ spend Meta của campaign có type đó trong tên. Vạch dọc = hoà vốn ${vn(be)} (sau giá vốn tạm và phí): bên trái vạch là <b>đang lỗ</b>.`} />
        {typed.length === 0 ? <div className="note">Khoảng này chưa có spend theo type.</div> : (
          <div className="chart-scroll"><div className="card wide-chart"><ResponsiveContainer width="100%" height={Math.max(200, 36 * typed.length)}>
            <BarChart data={typed} layout="vertical" margin={{ top: 8, right: 120, left: 8, bottom: 0 }}>
              <CartesianGrid stroke={C.line} horizontal={false} />
              <XAxis type="number" domain={[0, cap]} allowDataOverflow tickFormatter={(v) => vn(v, 1)} {...axis} />
              <YAxis type="category" dataKey="product_line" width={120} interval={0} {...axis} />
              <Tooltip cursor={{ fill: C.surface2 }} content={<Tip fmt={(v, p) => `${vn(p.payload.roas)} · rev ${money(p.payload.rev)} · spend ${money(p.payload.spend)} · ${p.payload.status}`} />} />
              <ReferenceLine x={be} stroke={C.muted} />
              <Bar isAnimationActive={false} name="ROAS" dataKey="plot" maxBarSize={18} radius={[0, 4, 4, 0]}>
                {typed.map((t) => <Cell key={t.product_line} fill={t.status === 'đang lỗ' ? C.crit : C.rev} />)}
                <LabelList dataKey="label" content={EndLabel} />
              </Bar>
            </BarChart>
          </ResponsiveContainer></div></div>)}
        <div className="cap" style={{ marginTop: 12 }}>
          Đang lỗ: <b>{d.lose_count}</b> type, spend <b>{money(d.lose_spend, 2)}</b>{d.lose_types.length ? ` (${d.lose_types.join(', ')})` : ''}.
          Spend chưa gán type (tên campaign kiểu cũ): <b>{money(d.untyped_spend, 2)}</b>. ROAS gán cả đơn tự nhiên, email cho type,
          nên type chi ít có ROAS cao giả: dùng để biết chỗ cần xem, chưa đủ để cắt ngân sách.
        </div>
        <Table rows={[...d.types].sort((a, b) => b.spend - a.spend)} cols={[
          { key: 'product_line', label: 'Type' }, { key: 'rev', label: 'Rev', num: true, fmt: (v) => vn(v) },
          { key: 'spend', label: 'Spend', num: true, fmt: (v) => vn(v) }, { key: 'roas', label: 'ROAS', num: true, fmt: (v) => vn(v) },
          { key: 'status', label: 'Trạng thái', cls: (r) => (r.status === 'đang lỗ' ? 'lose' : ''), fmt: (v) => (v === 'đang lỗ' ? '▼ đang lỗ' : v) },
        ]} />

        <Explorer title="Campaign theo kỳ chọn" rows={d.campaigns} nameKey="campaign_name" filterKey="ad_product_line" truncated={d.truncated} cols={[
          {key:'campaign_name',label:'Campaign'},{key:'ad_product_line',label:'Dòng'},
          {key:'spend',label:'Spend (USD)',num:true,fmt:v=>money(v,2)},
          {key:'ctr_pct',label:'CTR link',num:true,fmt:v=>pct(v,2)},
          {key:'cpm',label:'CPM (USD)',num:true,fmt:v=>money(v,2)},
          {key:'meta_purchases',label:'Mua (Meta)',num:true,fmt:v=>vn(v,0)},
          {key:'roas_meta',label:'ROAS Meta',num:true,fmt:v=>vn(v)}]}/>
        <p className="cap">Mua và ROAS Meta là số được Meta gán, không phải doanh thu gia tăng do quảng cáo.</p>

        <Sec title="Phễu Meta" cap="Số Meta tự nhận trong khoảng chọn, kèm % chuyển sang bước sau." />
        <div className="tiles six">{d.funnel.map((f) => (
          <Tile key={f.step} k={f.step} v={vn(f.value, 0)} d={f.note || (f.to_next_pct !== null ? `→ ${pct(f.to_next_pct, 2)} sang bước sau` : '')} />))}</div>
        <div className="cap">Đơn Shopify thật cùng kỳ: <b>{vn(d.orders, 0)}</b> (Meta tự nhận {vn(d.funnel.at(-1)?.value, 0)}: một phần đơn đến từ email, tự nhiên).</div>
      </>)
    }}</Guard>
  )
}
