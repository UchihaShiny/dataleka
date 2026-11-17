import { useEffect, useState } from 'react'

async function get(url, signal) {
  const r = await fetch(url, { signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(30000)]) : AbortSignal.timeout(30000) })
  const body = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(body.detail || body.error || `Lỗi ${r.status}`)
  return body
}

// Hỏi phiên bản dữ liệu mỗi 60 giây: nạp + dbt build xong thì version đổi, các trang tự tải lại số.
export function useMeta() {
  const [meta, setMeta] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    let stop = false
    const tick = () => get('/api/meta').then((m) => { if (!stop) { setMeta(m); setError(null) } })
      .catch((e) => !stop && setError(e.message))
    window.addEventListener('datae-retry', tick)
    tick()
    const id = setInterval(tick, 60_000)
    return () => { stop = true; clearInterval(id); window.removeEventListener('datae-retry', tick) }
  }, [])
  return { meta, error }
}

// Mỗi gói số gắn nhãn `for` = trang + khoảng ngày. Chỉ trả số khi nhãn khớp trang đang mở: 16/11 chuyển trang
// thì trang mới nhận nhầm số của trang cũ (Tổng quan) trong lúc tải, vỡ và làm trắng cả app.
// Cùng trang mà chỉ đổi phiên bản dữ liệu thì giữ số cũ tới khi có số mới (không nháy trắng).
export function usePage(name, preset, version) {
  const [retry, setRetry] = useState(0)
  useEffect(()=>{const f=()=>setRetry(r=>r+1);window.addEventListener('datae-retry',f);return()=>window.removeEventListener('datae-retry',f)},[])
  const key = `${name}?${preset}`
  const [state, setState] = useState({ for: null, loading: true, data: null, period: null, error: null })
  useEffect(() => {
    if (!version || !name) return   // name null = trang không có số theo khoảng ngày (Hỏi Claude, Báo cáo)
    let stop = false
    const controller=new AbortController()
    setState((s) => ({ ...s, loading: true }))
    get(`/api/page/${name}?preset=${preset}`, controller.signal)
      .then((r) => !stop && setState({ for: key, loading: false, data: r.data, period: r.period, error: null }))
      .catch((e) => !stop && setState({ for: key, loading: false, data: null, period: null, error: e.message }))
    return () => { stop = true; controller.abort() }
  }, [name, preset, version, key, retry])
  return state.for === key ? state : { for: key, loading: true, data: null, period: null, error: null }
}
