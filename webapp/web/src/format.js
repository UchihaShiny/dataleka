// Chart colors match the editorial surface tokens in theme.css.
export const THEMES = {
  light: {
    rev: '#34755f', spend: '#8a7968', crit: '#C42B2B', other: '#8A94A8',
    cat: ['#34755f', '#d95926', '#8a7968', '#B07600', '#d55181'],
    ink: '#252d2a', muted: '#626b64', line: '#deded4', surface: '#fffefa', surface2: '#f1efe8',
    seq: ['#f1efe8', '#CDEDE2', '#5CC3A3', '#34755f'],
  },
  dark: {
    rev: '#9ac6b4', spend: '#8a7968', crit: '#d03b3b', other: '#5D6880',
    cat: ['#9ac6b4', '#d95926', '#8a7968', '#c98500', '#d55181'],
    ink: '#f0f0e7', muted: '#b1bbb1', line: '#3c453e', surface: '#222824', surface2: '#2a322c',
    seq: ['#2a322c', '#12353A', '#9ac6b4', '#7FEBCB'],
  },
}
// C đổi tại chỗ khi đổi nền (applyTheme); các thành phần đọc C lúc vẽ, App vẽ lại cả trang.
export const C = { ...THEMES.light }
export function savedTheme() {
  try { const t = localStorage.getItem('datae-theme'); return t === 'dark' ? 'dark' : 'light' } catch { return 'light' }
}
export function applyTheme(name) {
  Object.assign(C, THEMES[name] || THEMES.light)
  document.documentElement.dataset.theme = name
  try { localStorage.setItem('datae-theme', name) } catch { /* không lưu được thì thôi */ }
}
const THU = ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7']

export function vn(x, digits = 2) {
  if (x === null || x === undefined || Number.isNaN(x)) return '–'
  return Number(x).toLocaleString('vi-VN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}
export const money = (x, d = 0) => (vn(x, d) === '–' ? '–' : `${vn(x, d)} $`)
export const pct = (x, d = 1, sign = false) =>
  vn(x, d) === '–' ? '–' : `${sign && x > 0 ? '+' : ''}${vn(x, d)}%`
export const short = (x) => (Math.abs(x) >= 1000 ? `${vn(x / 1000, 0)}k` : vn(x, 0))

// 'YYYY-MM-DD' → Date theo ngày (không lệch múi giờ)
export const toDate = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d) }
export const dm = (s) => { const d = toDate(s); return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}` }
export const dmy = (s) => `${dm(s)}/${toDate(s).getFullYear()}`
export const dayLabel = (s) => `${THU[toDate(s).getDay()]} ${dm(s)}`
// Tuần Chủ nhật → thứ Bảy, nhãn theo ngày đầu tuần: '2026-11-08' → '08–14/11'; qua tháng: '29/11–05/12'
export const weekEnd = (s) => { const d = toDate(s); d.setDate(d.getDate() + 6); return d }
export function weekRange(s) {
  const a = toDate(s), b = weekEnd(s), p = (n) => String(n).padStart(2, '0')
  return a.getMonth() === b.getMonth()
    ? `${p(a.getDate())}–${p(b.getDate())}/${p(b.getMonth() + 1)}`
    : `${dm(s)}–${p(b.getDate())}/${p(b.getMonth() + 1)}`
}
