"""Báo cáo của tôi: biểu đồ Claude đề xuất (khối ```report), Huy Anh xem trước rồi bấm Lưu.

Claude không tự lưu được gì: nó chỉ đưa spec. Backend kiểm trước khi chạy:
1. spec đúng dạng (check_spec): tiêu đề, kiểu biểu đồ, cột x/y.
2. SQL qua lọc chữ (check_sql_text): đúng 1 câu, bắt đầu bằng SELECT/WITH, không có lệnh ghi.
3. Dry run BigQuery (check_sql_bq): loại câu phải là SELECT, chỉ đọc bảng gold/silver của dự án, ≤ 50 MB.
Chạy bằng khoá CHỈ ĐỌC datae-mcp (khoá này cũng không có quyền ghi), tối đa MAX_ROWS dòng.
Lưu ở webapp/reports.json (biểu đồ) và webapp/analyses.json (bài phân tích), máy này, không vào git.
"""

import json
import os
import math
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / "webapp" / "reports.json"
ANALYSES = ROOT / "webapp" / "analyses.json"
if os.environ.get("DATAE_MODE") == "demo":
    _demo_dir = Path(os.environ.get("DATAE_DEMO_STORE", str(ROOT / "data" / "demo")))
    _demo_dir.mkdir(parents=True, exist_ok=True)
    STORE, ANALYSES = _demo_dir / "reports.json", _demo_dir / "analyses.json"

MAX_TEXT = 60_000
MAX_CHARTS = 3
MAX_BYTES = 50 * 1024 * 1024
MAX_ROWS = 500
CHARTS = ("bar", "line", "table")
DATASETS = ("gold", "silver")
WRITE_WORDS = ("insert", "update", "delete", "merge", "create", "drop", "alter", "truncate", "grant", "revoke",
               "call", "declare", "execute", "export", "load", "set", "begin", "commit", "rollback")
_lock = threading.Lock()


class ReportError(ValueError):
    pass


def check_spec(spec) -> dict:
    if not isinstance(spec, dict):
        raise ReportError("Báo cáo phải là object JSON.")
    title = str(spec.get("title") or "").strip()
    sql = str(spec.get("sql") or "").strip()
    chart = spec.get("chart")
    if not title or len(title) > 120:
        raise ReportError("Cần tiêu đề (tối đa 120 ký tự).")
    if not sql or len(sql) > 8000:
        raise ReportError("Cần câu SQL (tối đa 8.000 ký tự).")
    if chart not in CHARTS:
        raise ReportError(f"chart phải là một trong {', '.join(CHARTS)}.")
    out = {"title": title, "sql": sql, "chart": chart, "note": str(spec.get("note") or "").strip()[:300]}
    if chart != "table":
        x, y = spec.get("x"), spec.get("y")
        if isinstance(y, str):
            y = [y]
        if not isinstance(x, str) or not x:
            raise ReportError("Biểu đồ cần cột x.")
        if not isinstance(y, list) or not 1 <= len(y) <= 6 or not all(isinstance(v, str) and v for v in y):
            raise ReportError("Biểu đồ cần 1–6 cột y.")
        out.update(x=x, y=y, stack=bool(spec.get("stack")))
    return out


def _strip_literals(sql: str) -> str:
    """Bỏ chuỗi, tên trong backtick và chú thích để lọc chữ không bắt nhầm (ví dụ 'Short Sleeve update')."""
    sql = re.sub(r"--[^\n]*|#[^\n]*|/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`[^`]*`", " ", sql)


def check_sql_text(sql: str) -> str:
    sql = sql.strip().rstrip(";").strip()
    bare = _strip_literals(sql).lower()
    if ";" in bare:
        raise ReportError("Chỉ được 1 câu SQL.")
    if not re.match(r"^\s*\(?\s*(select|with)\b", bare):
        raise ReportError("SQL phải bắt đầu bằng SELECT hoặc WITH.")
    hit = [w for w in WRITE_WORDS if re.search(rf"\b{w}\b", bare)]
    if hit:
        raise ReportError(f"SQL có lệnh không cho phép: {', '.join(hit)}.")
    return sql


def check_sql_bq(c, sql: str) -> None:
    from google.cloud import bigquery

    job = c.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
    if job.statement_type != "SELECT":
        raise ReportError(f"Chỉ chạy câu SELECT (câu này là {job.statement_type}).")
    for t in job.referenced_tables or []:
        if t.project != c.project or t.dataset_id not in DATASETS:
            raise ReportError(f"Chỉ đọc gold/silver của dự án, không đọc {t.project}.{t.dataset_id}.{t.table_id}.")
    if (job.total_bytes_processed or 0) > MAX_BYTES:
        raise ReportError(f"Câu quét {job.total_bytes_processed / 1e6:.0f} MB, quá giới hạn 50 MB.")


def run(c, spec: dict) -> dict:
    """Kiểm rồi chạy 1 báo cáo. Trả {columns, rows}."""
    from google.cloud import bigquery

    from webapp.api.pages import clean

    spec = check_spec(spec)
    sql = check_sql_text(spec["sql"])
    check_sql_bq(c, sql)
    result = c.query(sql, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES)).result(max_results=MAX_ROWS)
    columns = [f.name for f in result.schema]
    rows = [clean({k: (float(v) if hasattr(v, "as_tuple") else v) for k, v in dict(r).items()}) for r in result]
    validate_chart_data(spec, columns, rows)
    return {"columns": columns, "rows": rows, "truncated": (result.total_rows or 0) > MAX_ROWS}


def validate_chart_data(spec: dict, columns: list[str], rows: list[dict]) -> None:
    """Reject text/object Y values instead of drawing misleading empty/zero charts."""
    if spec['chart'] == 'table':
        return
    missing = [key for key in [spec['x'], *spec['y']] if key not in columns]
    if missing:
        raise ReportError(f"Kết quả không có cột {', '.join(missing)} (có: {', '.join(columns)}).")
    for row in rows:
        for key in spec['y']:
            value = row.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise ReportError(f"Cột {key} cần giá trị số hoặc null. Chọn biểu đồ bảng nếu muốn xem văn bản.")
        if isinstance(row.get(spec['x']), (dict, list)):
            raise ReportError("Cột X phải là ngày, chữ hoặc số đơn giản.")


def load(path: Path | None = None) -> list[dict]:
    path = path or STORE
    if not path.exists():
        return []
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as error:
        raise ReportError("Không đọc được kho lưu. Giữ nguyên file để khôi phục từ bản sao lưu.") from error
    if not isinstance(items, list) or any(not isinstance(i, dict) or not i.get('id') for i in items):
        raise ReportError("Kho lưu sai cấu trúc; giữ nguyên file, chưa ghi thay đổi.")
    return items


def _write(items: list[dict], path: Path | None = None) -> None:
    path = path or STORE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _add(item: dict, path: Path) -> dict:
    with _lock:
        items = load(path)
        items.append(item)
        _write(items, path)
    return item


def _new_id() -> dict:
    return {"id": uuid.uuid4().hex[:12], "created": datetime.now().isoformat(timespec="seconds")}


def save(spec: dict) -> dict:
    spec = check_spec(spec)
    check_sql_text(spec["sql"])
    return _add({**_new_id(), **spec}, STORE)


def remove(report_id: str, path: Path | None = None) -> bool:
    path = path or STORE
    with _lock:
        items = load(path)
        kept = [r for r in items if r["id"] != report_id]
        if len(kept) == len(items):
            return False
        _write(kept, path)
    return True


def get(report_id: str) -> dict | None:
    return next((r for r in load() if r["id"] == report_id), None)


# Bài phân tích: BẢN CHỤP cố định (chữ Claude viết + biểu đồ kèm số lúc lưu), để sau này đọc lại đúng điều đã nói.
# Khác biểu đồ ở trên (chạy lại khi có số mới).

def save_analysis(c, body: dict, data_until: str | None, runner=None) -> dict:
    """Chạy lại các biểu đồ ngay lúc lưu và lưu kèm số. Biểu đồ nào lỗi thì không lưu cả bài (báo lỗi để sửa)."""
    title = str(body.get("title") or "").strip()
    text = str(body.get("text") or "").strip()
    specs = body.get("specs") or []
    if not title or len(title) > 160:
        raise ReportError("Cần tên bài (tối đa 160 ký tự).")
    if not text or len(text) > MAX_TEXT:
        raise ReportError(f"Cần nội dung (tối đa {MAX_TEXT:,} ký tự).".replace(",", "."))
    if not isinstance(specs, list) or len(specs) > MAX_CHARTS:
        raise ReportError(f"Tối đa {MAX_CHARTS} biểu đồ một bài.")
    charts = [{"spec": check_spec(s), "data": runner(s) if runner else run(c, s)} for s in specs]
    return _add({**_new_id(), "title": title, "question": str(body.get("question") or "").strip()[:4000],
                 "text": text, "data_until": data_until, "charts": charts}, ANALYSES)


def list_analyses() -> list[dict]:
    """Danh sách gọn (không kèm chữ và số) cho trang Báo cáo của tôi."""
    return [{k: a[k] for k in ("id", "created", "title", "data_until")} | {"charts": len(a["charts"])}
            for a in load(ANALYSES)]


def get_analysis(analysis_id: str) -> dict | None:
    return next((a for a in load(ANALYSES) if a["id"] == analysis_id), None)


def update(report_id: str, spec: dict):
    spec = check_spec(spec)
    check_sql_text(spec['sql'])
    with _lock:
        items = load()
        for i, item in enumerate(items):
            if item['id'] == report_id:
                items[i] = {**item, **spec, 'updated': datetime.now().isoformat(timespec='seconds')}
                _write(items)
                return items[i]
    return None
