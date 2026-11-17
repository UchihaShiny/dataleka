// Markdown gọn cho câu trả lời của Claude: đoạn, tiêu đề, danh sách, bảng |…|, khối code, **đậm**, `code`.
// Dựng thành phần React (không dùng innerHTML): chữ Claude trả về không chạy được như HTML.

function inline(text, key = 0) {
  const out = []
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g
  let last = 0, m, i = 0
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const t = m[0]
    out.push(t.startsWith('**') ? <b key={`${key}-${i++}`}>{t.slice(2, -2)}</b> : <code key={`${key}-${i++}`}>{t.slice(1, -1)}</code>)
    last = m.index + t.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

const cells = (line) => line.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
const isNum = (s) => /^[-+]?[\d.,]+\s*(%|\$|USD)?$/.test(s)

export function Markdown({ text }) {
  const lines = (text || '').split('\n')
  const blocks = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (line.startsWith('```')) {
      const body = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) body.push(lines[i++])
      i++
      blocks.push(<pre key={blocks.length}><code>{body.join('\n')}</code></pre>)
    } else if (line.trim().startsWith('|')) {
      const rows = []
      while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(lines[i++])
      const [head, ...rest] = rows
      const body = rest.filter((r) => !/^\s*\|?\s*:?-{2,}/.test(r)).map(cells)
      blocks.push(
        <div className="tbl md-tbl" key={blocks.length}><table>
          <thead><tr>{cells(head).map((c, j) => <th key={j}>{inline(c)}</th>)}</tr></thead>
          <tbody>{body.map((r, k) => <tr key={k}>{r.map((c, j) => <td key={j} className={isNum(c) ? 'num' : ''}>{inline(c)}</td>)}</tr>)}</tbody>
        </table></div>)
    } else if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\./.test(line)
      const items = []
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*([-*]|\d+\.)\s+/, ''))
      const L = ordered ? 'ol' : 'ul'
      blocks.push(<L key={blocks.length}>{items.map((t, k) => <li key={k}>{inline(t, k)}</li>)}</L>)
    } else if (/^#{1,4}\s/.test(line)) {
      blocks.push(<h4 key={blocks.length}>{inline(line.replace(/^#+\s/, ''))}</h4>)
      i++
    } else if (line.trim() === '') {
      i++
    } else {
      const para = []
      while (i < lines.length && lines[i].trim() !== '' && !/^(```|\s*\||\s*([-*]|\d+\.)\s|#{1,4}\s)/.test(lines[i])) para.push(lines[i++])
      blocks.push(<p key={blocks.length}>{para.map((p, k) => <span key={k}>{k > 0 && <br />}{inline(p, k)}</span>)}</p>)
    }
  }
  return <div className="md">{blocks}</div>
}
