// Báo cáo của tôi, 2 phần:
// - Bài phân tích: bản chụp cố định lúc lưu (chữ Claude viết + biểu đồ kèm số lúc đó), để đọc lại đúng điều đã nói.
// - Biểu đồ: chạy lại mỗi khi kho có số mới (theo phiên bản dữ liệu).
import { useEffect, useState } from 'react'
import { dmy } from '../format.js'
import { Markdown } from '../md.jsx'
import { api, ReportChart } from '../report.jsx'
import { Sec } from '../ui.jsx'
import ReportEditor from '../ReportEditor.jsx'

const when = (iso) => new Date(iso).toLocaleString('vi-VN', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit', year: 'numeric' })

function Analysis({ a, onDelete }) {
  const [open, setOpen] = useState(false)
  const [full, setFull] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    if (open && !full) api(`/api/analyses/${a.id}`).then(setFull).catch((e) => setError(e.message))
  }, [open, full, a.id])
  return (
    <section className="analysis">
      <div className="pv-head">
        <button className="an-title" onClick={() => setOpen(!open)} aria-expanded={open}>
          <span>{open ? '▾' : '▸'} {a.title}</span>
          <span className="an-meta">lưu {when(a.created)}{a.data_until && ` · số tới ${dmy(a.data_until)}`}{a.charts > 0 && ` · ${a.charts} biểu đồ`}</span>
        </button>
        <button className="btn ghost small" onClick={() => window.confirm(`Xoá bài "${a.title}"?`) && onDelete(a.id)}>Xoá</button>
      </div>
      {open && <div className="an-body">
        {error && <div className="note err">{error}</div>}
        {!full && !error && <div className="loading">Đang mở…</div>}
        {full && <>
          {full.question && <div className="cap">Câu hỏi: <b>{full.question}</b></div>}
          <Markdown text={full.text} />
          {full.charts.map((c, i) => <div key={i}><h4>{c.spec.title}</h4>{c.spec.note && <div className="cap">{c.spec.note}</div>}<ReportChart spec={c.spec} data={c.data} /></div>)}
        </>}
      </div>}
    </section>
  )
}

function One({ r, version, onDelete, onUpdate }) {
  const [s, setS] = useState({ loading: true })
  const [editing,setEditing]=useState(false)
  useEffect(() => {
    if (!version) return
    let stop = false
    setS({loading:true})
    api(`/api/reports/${r.id}/data`).then((d) => !stop && setS({ data: d.data })).catch((e) => !stop && setS({ error: e.message }))
    return () => { stop = true }
  }, [r, version])
  return (
    <section className="report">
      <div className="pv-head">
        <h4 className="rp-title">{r.title}</h4><button className="btn ghost small" onClick={()=>setEditing(!editing)}>Sửa</button>
        <button className="btn ghost small" onClick={() => window.confirm(`Xoá báo cáo "${r.title}"?`) && onDelete(r.id)}>Xoá</button>
      </div>
      {editing&&<ReportEditor id={r.id} initial={r} onCancel={()=>setEditing(false)} onSaved={v=>{onUpdate(v);setEditing(false)}}/>}
      {r.note && <div className="cap">{r.note}</div>}
      {s.loading && <div className="loading">Đang chạy…</div>}
      {s.error && <div className="note err">Không chạy được: {s.error}</div>}
      {s.data && <ReportChart spec={r} data={s.data} />}
      <details className="sql"><summary>SQL · lưu {new Date(r.created).toLocaleString('vi-VN')}</summary><pre><code>{r.sql}</code></pre></details>
    </section>
  )
}

export default function Reports({ meta }) {
  const [editor,setEditor]=useState(null)
  const [retry,setRetry]=useState(0)
  const [list, setList] = useState(null)
  const [articles, setArticles] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    api('/api/reports').then((b) => setList(b.reports)).catch((e) => setError(e.message))
    api('/api/analyses').then((b) => setArticles(b.analyses)).catch((e) => setError(e.message))
  }, [retry])
  const del = (id) => api(`/api/reports/${id}`, { method: 'DELETE' }).then(() => setList((l) => l.filter((x) => x.id !== id)))
    .catch((e) => setError(e.message))
  const delA = (id) => api(`/api/analyses/${id}`, { method: 'DELETE' }).then(() => setArticles((l) => l.filter((x) => x.id !== id)))
    .catch((e) => setError(e.message))
  if (error) return <div className="note err" role="alert">{error}<button className="btn ghost small" onClick={()=>{setError(null);setRetry(retry+1)}}>Thử lại</button></div>
  if (!list || !articles) return <div className="loading">Đang tải…</div>
  return (<>
    <div className="note"><b>Hai cách lưu.</b> Biểu đồ trực tiếp chạy lại SQL khi kho đổi; bản chụp giữ nguyên chữ và số lúc lưu. Xóa cần xác nhận và chỉ xóa mục đã chọn.</div>
    <div className="row"><button className="btn" onClick={()=>{if(meta?.mode==='demo')api('/api/demo/spec').then(setEditor).catch(e=>setError(e.message));else setEditor({title:'Biểu đồ mới',sql:'',chart:'line',x:'date',y:['rev']})}}>{meta?.mode==='demo'?'Tạo biểu đồ mẫu':'Tạo biểu đồ trực tiếp'}</button></div>
    {editor&&<ReportEditor initial={editor} onCancel={()=>setEditor(null)} onSaved={r=>{setList(l=>[...l,r]);setEditor(null)}}/>}
    <Sec title="Bài phân tích" cap="Bản chụp lúc lưu: chữ và số giữ nguyên, để sau này so lại Claude đã nói và dự báo gì." />
    {articles.length ? [...articles].reverse().map((a) => <Analysis key={a.id} a={a} onDelete={delA} />)
      : <div className="note">Chưa có bài nào. Ở <b>Hỏi Claude</b>, nhờ ví dụ "phân tích tuần trước", rồi bấm <b>Lưu bài phân tích</b> dưới câu trả lời.</div>}
    <Sec title="Biểu đồ (tự cập nhật)" cap="Chạy lại mỗi khi kho có số mới." />
    {list.length ? [...list].reverse().map((r) => <One key={r.id} r={r} version={meta?.version} onDelete={del} onUpdate={r=>setList(l=>l.map(x=>x.id===r.id?r:x))} />)
      : <div className="note">Chưa có biểu đồ nào. Ở <b>Hỏi Claude</b>, gõ "vẽ…", xem trước rồi bấm <b>Lưu biểu đồ</b>.</div>}
  </>)
}
