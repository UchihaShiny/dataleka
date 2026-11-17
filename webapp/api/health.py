"""Evidence from aggregate gold tables; observed coverage is not ingestion verification."""

from datetime import datetime, timezone
import yaml
from dashboard import queries as q
from webapp.api import pages


def definitions():
    return yaml.safe_load(
        (q.ROOT / "transform/metrics.yml").read_text(encoding="utf-8")
    )


def inspect(fetch, end):
    rows = pages.records(fetch(q.HEALTH, {"until": end}))
    from pipelines.dates import last_complete_day
    from datetime import date

    for row in rows:
        first, last = row["first_date"], row["last_date"]
        if first and last:
            from datetime import date

            row["calendar_days"] = (
                date.fromisoformat(last) - date.fromisoformat(first)
            ).days + 1
        else:
            row["calendar_days"] = None
        row["days_behind_clock"] = (
            max(0, (last_complete_day() - date.fromisoformat(last)).days)
            if last
            else None
        )
        row["verified_ingestion"] = None
    evidence = None
    from google.api_core.exceptions import NotFound

    try:
        st = fetch(q.LOAD_EVIDENCE, None)
        if not st.empty:
            evidence = pages.clean(st.iloc[0].to_dict())
    except NotFound:
        pass
    return {
        "sources": rows,
        "load": evidence,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "note": "Ngày có dòng ≠ ngày đã nạp đủ. Độ trễ = số ngày từ ngày cuối có dòng tới hôm qua Phoenix, không phải SLA nạp. built_at là lúc dbt dựng load_status, không phải lúc nguồn cập nhật. Không có bằng chứng đối soát hoặc giờ nạp từng nguồn trong gold; trạng thái đó chưa biết.",
    }
