import { useEffect, useState } from 'react'
import { useMeta, usePage } from './api.js'
import { applyTheme, dmy, savedTheme } from './format.js'
import { Boundary } from './ui.jsx'
import Overview from './pages/Overview.jsx'
import Ads from './pages/Ads.jsx'
import Products from './pages/Products.jsx'
import Customers from './pages/Customers.jsx'
import Alerts from './pages/Alerts.jsx'
import Ask from './pages/Ask.jsx'
import Reports from './pages/Reports.jsx'
import Trust from './pages/Trust.jsx'

const PAGES = [
  { id: 'overview', name: 'Tổng quan', View: Overview },
  { id: 'ads', name: 'Quảng cáo & type', View: Ads },
  { id: 'products', name: 'Sản phẩm', View: Products },
  { id: 'customers', name: 'Khách & email', View: Customers, fixed: true },   // fixed: mọi mục cố định (12 tuần, 60 ngày, RFM, cohort), không có bộ lọc ngày
  { id: 'alerts', name: 'Cảnh báo & dự báo', View: Alerts, fixed: true },   // luôn 14 ngày gần nhất + 14 ngày tới
  { id: 'trust', name: 'Chỉ số & dữ liệu', View: Trust, tool: true },
  { id: 'ask', name: 'Hỏi Claude', View: Ask, tool: true },          // tool: không có số theo khoảng ngày
  { id: 'reports', name: 'Báo cáo của tôi', View: Reports, tool: true },
]
const PRESETS = [['7', '7 ngày'], ['14', '14 ngày'], ['28', '28 ngày'], ['month', 'Tháng này']]

// trang + khoảng ngày nằm trên URL (#ads?preset=28): tải lại vẫn giữ chỗ đang xem
function readHash() {
  const [p, qs] = window.location.hash.slice(1).split('?')
  const preset = new URLSearchParams(qs || '').get('preset')
  return { page: PAGES.some((x) => x.id === p) ? p : 'overview', preset: PRESETS.some(([k]) => k === preset) ? preset : '7' }
}

export default function App() {
  const [{ page, preset }, setNav] = useState(readHash)
  const [open, setOpen] = useState(false)
  const [theme, setTheme] = useState(savedTheme)
  const flip = () => { const next = theme === 'dark' ? 'light' : 'dark'; applyTheme(next); setTheme(next) }
  const { meta, error } = useMeta()
  useEffect(() => { const f=(e)=>{if(e.key==='Escape')setOpen(false)}; window.addEventListener('keydown',f); return ()=>window.removeEventListener('keydown',f) }, [])
  useEffect(() => {
    const [route,qs]=window.location.hash.slice(1).split('?')
    const params=new URLSearchParams(route===page ? qs : '')
    params.set('preset',preset)
    const next=`${page}?${params}`
    if(window.location.hash.slice(1)!==next)window.location.hash=next
  }, [page, preset])
  useEffect(() => { const f = () => setNav(readHash()); window.addEventListener('hashchange', f); return () => window.removeEventListener('hashchange', f) }, [])
  const current = PAGES.find((x) => x.id === page)
  const state = usePage(current.tool ? null : page, current.fixed ? '7' : preset, meta?.version)   // trang cố định: 1 bản cache
  const go = (next) => { setNav((s) => ({ ...s, ...next })); setOpen(false) }
  const updated = meta ? new Date(meta.version).toLocaleString('vi-VN', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }) : null

  return (
    <div className="layout">
      <a className="skip-link" href="#content" onClick={e=>{e.preventDefault();document.getElementById('content').focus()}}>Đến nội dung</a>
      {open && <button className="menu-scrim" onClick={()=>setOpen(false)} aria-label="Đóng menu" />}
      <aside className={`side ${open ? 'open' : ''}`}>
        <div className="brand"><div className="logo">D<span>↗</span></div><div><div className="bname">DEERLY’S</div><div className="bsub">BUSINESS INTELLIGENCE</div></div></div><div className="workspace-label">WORKSPACE <span>DataE / 01</span></div>
        <nav className="nav" aria-label="Trang">
          {PAGES.filter((x) => !x.tool).map((x) => <button key={x.id} className={x.id === page ? 'on' : ''} aria-current={x.id === page ? 'page' : undefined} onClick={() => go({ page: x.id })}><span className="nav-icon" aria-hidden="true">{({overview:'◫',ads:'↗',products:'◇',customers:'◎',alerts:'⌁',trust:'⊞',ask:'✳',reports:'▤'})[x.id]}</span>{x.name}</button>)}
        </nav>
        <div className="side-label">CÔNG CỤ</div>
        <nav className="nav" aria-label="Claude">
          {PAGES.filter((x) => x.tool).map((x) => <button key={x.id} className={x.id === page ? 'on' : ''} aria-current={x.id === page ? 'page' : undefined} onClick={() => go({ page: x.id })}><span className="nav-icon" aria-hidden="true">{({overview:'◫',ads:'↗',products:'◇',customers:'◎',alerts:'⌁',trust:'⊞',ask:'✳',reports:'▤'})[x.id]}</span>{x.name}</button>)}
        </nav>
        <button className="theme-btn" onClick={flip}>{theme === 'dark' ? '☀ Nền sáng' : '☾ Nền tối'}</button>
        <div className="side-foot">
          Ngày kinh doanh America/Phoenix<br />
          Số mới nhất đã trọn: <span className="mono">{meta ? dmy(meta.end_max) : '…'}</span><br />
          {updated && <span className="fresh">Bảng sửa gần nhất {updated}</span>}<br /><br />
          Trang tự tải số mới sau khi nạp dữ liệu (kiểm mỗi 60 giây). Hỏi chi tiết: trang Hỏi Claude.
        </div>
      </aside>
      <div>
        <div className="topbar"><button onClick={() => setOpen(!open)} aria-expanded={open} aria-label="Mở menu">☰ Menu</button><b>{current.name}</b></div>
        <main id="content" tabIndex={-1} onClick={() => open && setOpen(false)}>
          <div className="page-top"><span>DEERLY’S / ANALYTICS</span><div className="page-actions"><button className="refresh-btn" onClick={()=>window.dispatchEvent(new Event('datae-retry'))} title="Tải lại số từ backend hiện tại">↻ Làm mới</button><span className="pv-tag">{meta?.mode==='demo'?'DEMO · GIẢ LẬP':'CHỈ ĐỌC'}</span></div></div>
          {meta?.mode==='demo' && <div className="demo-banner" role="status">Dữ liệu giả lập cố định · không kết nối Shopify, Meta, Klaviyo hay Claude. Nội dung lưu tách biệt với bản thật.</div>}
          <div className="eyebrow">DataE · {current.tool || current.fixed ? `số tới ${meta ? dmy(meta.end_max) : '…'}`
            : state.period ? `${dmy(state.period.start)} → ${dmy(state.period.end)}` : '…'}</div>
          <h1 className="title">{current.name}<span className="title-dot">.</span></h1>
          <p className="page-subtitle">{({overview:'Từ dữ liệu mỗi ngày đến quyết định tiếp theo.',ads:'Hiểu hiệu quả chi tiêu và những dòng sản phẩm cần xem kỹ.',products:'Khám phá thiết kế, doanh thu và hành vi hoàn trả.',customers:'Nhìn sâu hơn vào những lần khách hàng quay lại.',alerts:'Theo dõi điều khác thường. Đặt kỳ vọng có cơ sở.',ask:'Đặt câu hỏi. Xem bằng chứng. Giữ lại điều hữu ích.',reports:'Không gian lưu giữ biểu đồ và các góc nhìn của bạn.',trust:'Một định nghĩa chung. Bằng chứng dữ liệu rõ ràng.'})[page]}</p>
          {!current.tool && !current.fixed && <div className="presets" role="group" aria-label="Khoảng ngày">
            {PRESETS.map(([k, label]) => <button key={k} className={k === preset ? 'on' : ''} aria-pressed={k === preset}
              onClick={() => go({ preset: k })}>{label}</button>)}
          </div>}
          {error && <div className="note err" role="alert">Không nối được backend: {error} <button className="btn ghost small" onClick={()=>window.dispatchEvent(new Event('datae-retry'))}>Thử lại</button></div>}
          <Boundary resetKey={`${page}?${preset}`}><current.View state={state} meta={meta} /></Boundary>
        </main>
      </div>
    </div>
  )
}
