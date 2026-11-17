"""Backend dashboard React của DataE (chạy trên máy, http://127.0.0.1:8600).

- /api/meta           phiên bản dữ liệu + ngày trọn cuối + hoà vốn (trang hỏi mỗi 60 giây)
- /api/page/{tên}     số của 1 trang: overview | ads | products | customers | alerts; ?preset=7|14|28|month
- /api/chat           hỏi Claude (Claude Code CLI, gói Max; chỉ 2 server MCP chỉ đọc), trả SSE
- /api/reports        Báo cáo của tôi: xem trước, lưu, chạy, xoá (webapp/api/reports.py kiểm SQL)
- /                   React đã build (webapp/web/dist)

Tự có số mới: "phiên bản" = lần sửa cuối của các bảng gold (metadata BigQuery, miễn phí). Cache kết quả theo
(trang, khoảng ngày, phiên bản): nạp + dbt build xong là phiên bản đổi, lần hỏi kế tiếp đọc số mới.
Chỉ khoá CHỈ ĐỌC datae-mcp (dashboard/queries.readonly_client); chỉ nghe 127.0.0.1.

Chạy tay (thử):  python -m uvicorn webapp.api.main:app --port 8600
"""

import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from dashboard import kpi  # noqa: E402
from dashboard import queries as q  # noqa: E402
from pipelines.dates import last_complete_day  # noqa: E402
from webapp.api import claude_chat, pages, reports, health, chat_stream

DEMO = os.environ.get("DATAE_MODE", "live") == "demo"
if os.environ.get("DATAE_MODE", "live") not in ("live", "demo"):
    raise RuntimeError("DATAE_MODE phải là live hoặc demo")
if DEMO:
    from webapp.api import demo  # noqa: E402

DIST = ROOT / "webapp" / "web" / "dist"
VERSION_TTL = 30          # giây: hỏi metadata BigQuery tối đa 1 lần / 30 giây
CACHE_MAX = 200

app = FastAPI(title="DataE dashboard", docs_url=None, redoc_url=None)
_lock = threading.Lock()
_state = {"client": None, "version": None, "version_at": 0.0, "cache": {}}


@app.exception_handler(reports.ReportError)
async def storage_error(request: Request, error: reports.ReportError):
    return JSONResponse({"detail": str(error)}, status_code=400)


@app.exception_handler(Exception)
async def service_error(request: Request, error: Exception):
    return JSONResponse({"detail": "Dịch vụ dữ liệu chưa sẵn sàng. Kiểm tra kết nối/cấu hình chỉ đọc rồi thử lại; không thay bằng dữ liệu demo."}, status_code=503)


def client():
    if _state["client"] is None:
        try:
            _state["client"] = q.readonly_client()
        except q.ReadOnlyKeyError as error:
            raise HTTPException(503, str(error))
    return _state["client"]


def version() -> str:
    if DEMO:
        return demo.VERSION
    now = time.time()
    if _state["version"] is None or now - _state["version_at"] > VERSION_TTL:
        new = q.data_version(client())
        changed = new != _state["version"]
        _state["version"], _state["version_at"] = new, now
        if changed:   # vừa nạp/build: tính sẵn 5 trang ở chế độ 7 ngày, mở trang khỏi chờ 3–7 giây
            threading.Thread(target=warm, args=(new,), daemon=True).start()
    return _state["version"]


def warm(v: str, preset: str = "7") -> None:
    try:
        from concurrent.futures import ThreadPoolExecutor

        ctx = cached(("ctx", preset, v), lambda: pages.context(fetch, last_complete_day(), preset))
        # song song 5 trang: lần lượt mất ~25 giây (16/11), song song ~7 giây (trang chậm nhất)
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(lambda item: cached((item[0], preset, v), lambda: item[1](fetch, ctx)),
                          pages.PAGES.items()))
    except Exception as error:  # chỉ là tính sẵn: lỗi thì lần mở trang sẽ tính lại và báo lỗi thật
        print(f"warm lỗi: {error}", file=sys.stderr)


def fetch(sql, params):
    return demo.fetch(sql, params) if DEMO else q.run(client(), sql, params)


def cached(key, make):
    with _lock:
        hit = _state["cache"].get(key)
    if hit is not None:
        return hit
    value = make()
    with _lock:
        if len(_state["cache"]) > CACHE_MAX:
            _state["cache"].clear()
        _state["cache"][key] = value
    return value


@app.get("/api/meta")
def meta():
    v = version()
    ctx = cached(("ctx", "7", v), lambda: pages.context(fetch, last_complete_day(), "7"))
    cogs, fee = kpi.rates()
    return JSONResponse(pages.clean({"version": v, "end_max": ctx["end_max"], "breakeven": ctx["breakeven"],
                                     "cogs_rate": cogs, "fee_rate": fee, "presets": pages.PRESET_KEYS, "mode": "demo" if DEMO else "live", "timezone": "America/Phoenix"}))


@app.get("/api/page/{name}")
def page(name: str, preset: str = "7"):
    if name not in pages.PAGES:
        raise HTTPException(404, f"Không có trang {name}")
    if preset not in pages.PRESET_KEYS:
        raise HTTPException(400, f"preset phải là một trong {list(pages.PRESET_KEYS)}")
    v = version()
    ctx = cached(("ctx", preset, v), lambda: pages.context(fetch, last_complete_day(), preset))
    data = cached((name, preset, v), lambda: pages.PAGES[name](fetch, ctx))
    return JSONResponse({"version": v, "period": pages.clean({k: ctx[k] for k in
                                                                ("start", "end", "p_start", "p_end", "end_max")}),
                         "data": data})


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session: str | None = Field(default=None, pattern=r"^[0-9a-fA-F-]{36}$")


class SpecIn(BaseModel):
    spec: dict


@app.post("/api/chat")
def chat(body: ChatIn, request: Request):
    """Read-only chat, bounded event queue; disconnect stops the CLI worker."""
    project = "demo" if DEMO else client().project
    produce = (lambda stop: demo.ask(body.message)) if DEMO else (
        lambda stop: claude_chat.ask(body.message, project, body.session, cancel=stop))
    return StreamingResponse(chat_stream.response_events(request, produce), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _report_data(spec: dict) -> dict:
    try:
        return demo.run_report(spec) if DEMO else reports.run(client(), spec)
    except reports.ReportError as error:
        raise HTTPException(400, str(error))
    except Exception as error:   # lỗi BigQuery (sai tên cột, sai cú pháp...): trả nguyên văn để sửa
        raise HTTPException(400, f"BigQuery báo lỗi: {getattr(error, 'message', None) or error}")


@app.post("/api/reports/preview")
def report_preview(body: SpecIn):
    data = _report_data(body.spec)   # kiểm spec + SQL trước, sai thì 400
    return JSONResponse({"spec": reports.check_spec(body.spec), "data": data})


@app.get("/api/reports")
def report_list():
    return JSONResponse({"reports": reports.load()})


@app.post("/api/reports")
def report_save(body: SpecIn):
    _report_data(body.spec)   # chạy được mới lưu
    return JSONResponse(reports.save(body.spec))


@app.get("/api/reports/{report_id}/data")
def report_data(report_id: str):
    spec = reports.get(report_id)
    if spec is None:
        raise HTTPException(404, "Không có báo cáo này.")
    v = version()
    return JSONResponse({"version": v, "data": cached(("report", report_id, v), lambda: _report_data(spec))})


@app.delete("/api/reports/{report_id}")
def report_delete(report_id: str):
    if not reports.remove(report_id):
        raise HTTPException(404, "Không có báo cáo này.")
    return JSONResponse({"ok": True})


class AnalysisIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=60000)
    question: str = Field(default="", max_length=4000)
    specs: list[dict] = Field(default_factory=list)


@app.get("/api/analyses")
def analysis_list():
    return JSONResponse({"analyses": reports.list_analyses()})


@app.post("/api/analyses")
def analysis_save(body: AnalysisIn):
    """Lưu bài phân tích: bản chụp chữ + biểu đồ (chạy lại ngay để lưu kèm số)."""
    ctx = cached(("ctx", "7", version()), lambda: pages.context(fetch, last_complete_day(), "7"))
    try:
        item = reports.save_analysis(None if DEMO else client(), body.model_dump(), pages.clean(ctx["end_max"]), runner=_report_data)
    except reports.ReportError as error:
        raise HTTPException(400, str(error))
    except Exception as error:
        raise HTTPException(400, f"BigQuery báo lỗi: {getattr(error, 'message', None) or error}")
    return JSONResponse({k: item[k] for k in ("id", "created", "title", "data_until")})


@app.get("/api/analyses/{analysis_id}")
def analysis_get(analysis_id: str):
    item = reports.get_analysis(analysis_id)
    if item is None:
        raise HTTPException(404, "Không có bài này.")
    return JSONResponse(item)


@app.delete("/api/analyses/{analysis_id}")
def analysis_delete(analysis_id: str):
    if not reports.remove(analysis_id, reports.ANALYSES):
        raise HTTPException(404, "Không có bài này.")
    return JSONResponse({"ok": True})


@app.get("/api/definitions")
def metric_definitions():
    return health.definitions()


@app.get("/api/health")
def data_health():
    v = version()
    ctx = cached(("ctx", "7", v), lambda: pages.context(fetch, last_complete_day(), "7"))
    return cached(("health", v, last_complete_day()), lambda: health.inspect(fetch, ctx["end_max"]))


@app.get("/api/demo/spec")
def demo_spec():
    if not DEMO:
        raise HTTPException(404, "Chỉ có trong demo")
    return demo.SPEC


@app.put("/api/reports/{report_id}")
def report_update(report_id: str, body: SpecIn):
    _report_data(body.spec)
    item = reports.update(report_id, body.spec)
    if item is None:
        raise HTTPException(404, "Không có báo cáo này")
    with _lock:
        _state["cache"].clear()
    return item


@app.get("/api/{path:path}")
def api_not_found(path: str):
    raise HTTPException(404, "API không tồn tại")


if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}")
def spa(path: str):
    index = DIST / "index.html"
    if not index.exists():
        return JSONResponse({"error": "Chưa build giao diện: cd webapp/web && npm run build"}, status_code=503)
    return FileResponse(index)
