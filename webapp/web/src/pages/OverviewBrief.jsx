import {dm,money,pct,vn} from '../format.js'
export default function OverviewBrief({data,period}) {
 const {totals:t,change,comparable}=data
 const preset=new URLSearchParams(location.hash.split('?')[1]).get('preset')||'7'
 const complete=t.days===data.expected_days
 return <section className="overview-brief" aria-label="Tóm tắt kỳ kinh doanh">
  <div className="brief-main"><span className="brief-kicker">THE BUSINESS PULSE</span><h2>Mỗi con số.<br/><em>Một góc nhìn rõ hơn.</em></h2><p>{dm(period.start)}–{dm(period.end)} · {t.days}/{data.expected_days} ngày có dữ liệu · USD</p><a className="brief-link" href={`#ads?preset=${preset}`}>Khám phá hiệu quả quảng cáo <span aria-hidden="true">↗</span></a></div>
  <div className="brief-facts"><div className="brief-fact"><span>Doanh thu trong kỳ</span><strong>{money(t.rev)}</strong><small>{comparable ? `${pct(change.rev,1,true)} so kỳ trước tương đương`:'Chưa đủ bằng chứng để so sánh kỳ trước'}</small></div><div className="brief-fact"><span>Hiệu quả doanh thu / chi phí</span><strong>{vn(t.mer)}<small> MER</small></strong><small>Tính từ tổng Rev ÷ tổng spend</small></div></div>
  <div className="brief-foot"><span className="brief-status">{complete?'Đủ ngày trong kỳ chọn':'Kỳ chọn còn thiếu ngày'}</span><span>Ngày Phoenix · chỉ ngày đã trọn</span><a href="#trust">Nguồn & định nghĩa ↗</a></div>
 </section>
}
