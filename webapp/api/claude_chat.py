"""Hỏi Claude từ dashboard: gọi Claude Code CLI đã đăng nhập (gói Max của Huy Anh), không dùng Claude API.

Khoá an toàn (tests/test_claude_chat.py kiểm từng cái):
- `--tools ""`: tắt mọi tool có sẵn (Bash, Read, Edit, WebFetch...). Claude không chạm được file, không đọc được .env.
- `--strict-mcp-config` + file MCP riêng: chỉ 2 server chỉ đọc `datae` và `datae-sql` (khoá datae-mcp), bỏ qua
  mọi MCP khác của máy. `--allowedTools` chỉ 2 server đó; `--permission-mode dontAsk`: tool khác tự bị từ chối.
- Chạy trong thư mục làm việc riêng ngoài dự án: không nạp CLAUDE.md, .claude/settings của DataE.
- Dòng `init` của Claude liệt kê tool thật có trong phiên: thấy tool nào ngoài 2 server trên thì dừng ngay.
- Claude KHÔNG lưu được gì. Muốn biểu đồ thì nó chỉ trả khối ```report (JSON); backend tự kiểm và chạy
  (webapp/api/reports.py), Huy Anh bấm Lưu mới lưu.

Chỉ cho 1 người dùng trên máy này (tài khoản Claude cá nhân); mỗi lần 1 câu; quá TIMEOUT giây thì dừng.

Thử tay (dùng đăng nhập Claude + khoá datae-mcp):  python -m webapp.api.claude_chat "MER 7 ngày qua?"
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKDIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "DataE" / "claude-chat"
TIMEOUT = 180                       # giây cho 1 câu (gồm mọi lần gọi tool)
ALLOWED_SERVERS = ("datae", "datae-sql")
REPORT_RE = re.compile(r"```report\s*\n(.*?)\n```", re.S)
MAX_CHARTS = 3                      # biểu đồ tối đa trong 1 câu trả lời

SYSTEM = """Bạn trả lời câu hỏi về số liệu shop DEERLY'S trên dashboard DataE của Huy Anh. Luôn trả lời tiếng Việt, ngắn gọn.
- Chỉ dùng tool của 2 server datae và datae-sql (chỉ đọc). Không có tool nào khác.
- Ngày là ngày kinh doanh giờ America/Phoenix; gọi today_phoenix để biết ngày nên tính tới (use_until). Kho có số trọn tới gold.load_status.complete_through.
- Câu quen (MER, ROAS theo type, email, khách, dự báo...) dùng tool datae; câu lạ thì tự viết SQL bằng execute_sql của datae-sql.
- Số tiền là USD. Tỉ lệ (MER, ROAS, CPO) tính từ tổng, không lấy trung bình từng ngày.

- Khi được nhờ phân tích hay báo cáo: nêu số chính, so với kỳ trước, nguyên nhân có thể (chỉ từ số đọc được), dự báo nếu được hỏi (forecast_orders), và 1–3 việc nên làm. Ghi rõ khoảng ngày đã dùng. Người dùng có thể lưu nguyên câu trả lời thành "bài phân tích", nên viết để đọc lại sau vẫn hiểu.

Khi người dùng muốn biểu đồ, hoặc bài phân tích cần biểu đồ để dễ thấy, sau phần trả lời thêm 1 đến 3 khối (mỗi biểu đồ 1 khối):
```report
{"title": "...", "sql": "select ...", "chart": "bar|line|table", "x": "cột trục ngang", "y": ["cột số", "..."], "stack": false, "note": "1 câu nói số này là gì"}
```
Quy tắc khối report:
- sql là 1 câu SELECT BigQuery (không dấu ; cuối), tên bảng đầy đủ `{project}.gold.<bảng>` hoặc `{project}.silver.<bảng>`, có ORDER BY, tối đa 500 dòng.
- Khoảng ngày viết tương đối theo ngày trọn cuối (ví dụ date between date_sub(<ngày trọn cuối>, interval 55 day) and <ngày trọn cuối>, với ngày trọn cuối = (select complete_through from `{project}.gold.load_status`)) để báo cáo tự cập nhật khi có số mới.
- Theo tuần thì tuần Chủ nhật → thứ Bảy (date_trunc(date, week(sunday))), chỉ lấy tuần đã trọn, không lấy tuần đang dở.
- Chạy thử câu SQL bằng execute_sql trước khi đưa vào khối, tên cột x, y phải đúng tên cột trả về; y là cột số.
- chart "table" thì bỏ x, y. Câu hỏi số đơn giản thì không cần khối report.
Bạn không lưu được gì; người dùng xem trước rồi tự bấm Lưu."""

_busy = threading.Lock()


class ChatError(RuntimeError):
    pass


def claude_exe() -> str:
    """claude.exe thật (gói npm cài bản native). Gọi thẳng exe, không qua claude.cmd: cmd.exe làm hỏng dấu nháy."""
    npm = Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    if npm.exists():
        return str(npm)
    found = shutil.which("claude")
    if not found:
        raise ChatError("Không thấy Claude Code trên máy (lệnh claude).")
    return found


def mcp_config() -> dict:
    """2 server chỉ đọc, đường dẫn tuyệt đối (chạy từ thư mục làm việc riêng)."""
    py = sys.executable
    return {"mcpServers": {
        "datae": {"command": py, "args": [str(ROOT / "mcp_server" / "server.py")]},
        "datae-sql": {"command": py, "args": [str(ROOT / "mcp_toolbox" / "run.py")]},
    }}


def prepare_workdir() -> Path:
    WORKDIR.mkdir(parents=True, exist_ok=True)
    (WORKDIR / "mcp.json").write_text(json.dumps(mcp_config(), ensure_ascii=False, indent=1), encoding="utf-8")
    return WORKDIR


def command(project: str, session_id: str | None = None, exe: str | None = None) -> list[str]:
    if session_id and not re.fullmatch(r"[0-9a-fA-F-]{36}", session_id):
        raise ChatError("session_id không hợp lệ.")
    cmd = [exe or claude_exe(), "-p",
           "--output-format", "stream-json", "--verbose", "--include-partial-messages",
           "--tools", "",
           "--strict-mcp-config", "--mcp-config", str(WORKDIR / "mcp.json"),
           "--allowedTools", *[f"mcp__{s}" for s in ALLOWED_SERVERS],
           "--permission-mode", "dontAsk",
           "--setting-sources", "project",
           "--append-system-prompt", SYSTEM.replace("{project}", project)]
    if session_id:
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", session_id):
            raise ChatError("session_id không hợp lệ.")
        cmd += ["--resume", session_id]
    return cmd


def tool_allowed(name: str) -> bool:
    return any(name.startswith(f"mcp__{s}__") for s in ALLOWED_SERVERS)


def split_reports(text: str) -> tuple[str, list[dict], list[str]]:
    """Tách mọi khối ```report (tối đa MAX_CHARTS) khỏi câu trả lời. Trả (chữ còn lại, các spec, các lỗi đọc JSON)."""
    specs, errors = [], []
    for m in REPORT_RE.finditer(text or ""):
        try:
            spec = json.loads(m.group(1))
            if not isinstance(spec, dict):
                raise ValueError("không phải object")
            specs.append(spec)
        except ValueError as error:
            errors.append(f"Khối report không đọc được: {error}")
    if len(specs) > MAX_CHARTS:
        errors.append(f"Chỉ lấy {MAX_CHARTS} biểu đồ đầu.")
    return REPORT_RE.sub("", text or "").strip(), specs[:MAX_CHARTS], errors


def events(lines, on_tools=None):
    """Đổi từng dòng stream-json của Claude Code thành sự kiện gọn cho trang:
    session, text (từng đoạn chữ), tool (tên tool đang gọi), done (chữ cuối + report), error."""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        kind = ev.get("type")
        if kind == "system" and ev.get("subtype") == "init":
            bad = [t for t in ev.get("tools", []) if not tool_allowed(t)]
            if bad:
                if on_tools:
                    on_tools(bad)
                yield {"t": "error", "msg": f"Dừng: phiên Claude có tool ngoài 2 server chỉ đọc ({', '.join(bad[:5])})."}
                return
            down = [s.get("name") for s in ev.get("mcp_servers", []) if s.get("status") != "connected"]
            if down:
                yield {"t": "warn", "msg": f"Server chưa nối được: {', '.join(down)}"}
            yield {"t": "session", "id": ev.get("session_id")}
        elif kind == "stream_event":
            e = ev.get("event", {})
            if e.get("type") == "content_block_delta" and e.get("delta", {}).get("type") == "text_delta":
                yield {"t": "text", "s": e["delta"]["text"]}
        elif kind == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    yield {"t": "tool", "name": block.get("name", "").replace("mcp__", "").replace("__", " · ")}
        elif kind == "result":
            if ev.get("is_error") or ev.get("subtype") != "success":
                yield {"t": "error", "msg": str(ev.get("result") or ev.get("subtype") or "Claude báo lỗi.")}
                return
            text, specs, errs = split_reports(ev.get("result", ""))
            yield {"t": "done", "text": text, "reports": specs, "report_errors": errs, "session": ev.get("session_id")}
            return


def ask(message: str, project: str, session_id: str | None = None, cancel=None):
    """Chạy 1 câu hỏi, sinh từng sự kiện. Câu hỏi đi qua stdin (không qua dòng lệnh)."""
    message = (message or "").strip()
    if not message:
        yield {"t": "error", "msg": "Câu hỏi trống."}
        return
    if len(message) > 4000:
        yield {"t": "error", "msg": "Câu hỏi dài quá 4.000 ký tự."}
        return
    if not _busy.acquire(blocking=False):
        yield {"t": "error", "msg": "Claude đang trả lời câu trước, đợi xong rồi hỏi tiếp."}
        return
    proc = None
    watcher_done = threading.Event()
    try:
        prepare_workdir()
        cmd = command(project, session_id)
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        proc = subprocess.Popen(cmd, cwd=WORKDIR, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, env=env, encoding="utf-8", errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        proc.stdin.write(message)
        proc.stdin.close()
        def watch_cancel():
            while not watcher_done.wait(0.05):
                if cancel is not None and cancel.is_set():
                    if proc.poll() is None:
                        proc.kill()
                    return
        if cancel is not None:
            threading.Thread(target=watch_cancel, daemon=True, name='datae-chat-cancel').start()
        timer = threading.Timer(TIMEOUT, proc.kill)
        timer.start()
        started, finished = time.time(), False
        try:
            for ev in events(proc.stdout, on_tools=lambda _: proc.kill()):
                finished = finished or ev["t"] in ("done", "error")
                if cancel is not None and cancel.is_set():
                    return
                yield ev
        finally:
            timer.cancel()
        if cancel is not None and cancel.is_set():
            return
        if not finished:
            waited = time.time() - started
            yield {"t": "error", "msg": f"Quá {TIMEOUT} giây, đã dừng." if waited >= TIMEOUT - 1
                   else "Claude dừng giữa chừng. Kiểm tra đăng nhập Claude và kết nối hai MCP chỉ đọc rồi thử lại."}
    except (ChatError, OSError) as error:
        yield {"t": "error", "msg": str(error)}
    finally:
        watcher_done.set()
        if proc and proc.poll() is None:
            proc.kill()
        _busy.release()


if __name__ == "__main__":   # thử tay: in từng sự kiện
    sys.path.insert(0, str(ROOT))
    from dashboard import queries as q

    for item in ask(" ".join(sys.argv[1:]) or "MER 7 ngày qua?", q.readonly_client().project):
        print(json.dumps(item, ensure_ascii=False))
