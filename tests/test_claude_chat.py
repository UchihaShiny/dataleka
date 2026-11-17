"""Kiểm trang Hỏi Claude + Báo cáo của tôi (webapp/api/claude_chat.py, reports.py) bằng dữ liệu giả:
không gọi Claude thật, không BigQuery, không dùng khoá.

Chạy từ thư mục gốc:  python tests/test_claude_chat.py
"""

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from webapp.api import claude_chat as cc  # noqa: E402
from webapp.api import reports as rp  # noqa: E402

SPEC = {"title": "Doanh thu theo type", "chart": "bar", "x": "tuan", "y": ["rev"], "stack": True,
        "sql": "select tuan, rev from `datae-514203.gold.mart_type_day` order by tuan"}


def raises(fn, *args, contains=""):
    try:
        fn(*args)
    except (rp.ReportError, cc.ChatError) as error:
        assert contains in str(error), str(error)
        return
    raise AssertionError(f"phải báo lỗi: {args}")


def test_lenh_khoa_chat():
    cmd = cc.command("datae-514203", exe="claude.exe")
    assert cmd[cmd.index("--tools") + 1] == "", "tắt hết tool có sẵn (Bash, Read, Edit...)"
    assert "--strict-mcp-config" in cmd and cmd[cmd.index("--mcp-config") + 1].endswith("mcp.json")
    i = cmd.index("--allowedTools")
    assert cmd[i + 1:i + 3] == ["mcp__datae", "mcp__datae-sql"] and cmd[i + 3].startswith("--")
    assert cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
    assert not any("dangerously" in a or a == "bypassPermissions" for a in cmd)
    assert "{project}" not in " ".join(cmd) and "datae-514203.gold" in cmd[cmd.index("--append-system-prompt") + 1]
    assert "--resume" not in cmd
    sid = "0f3c2d4e-1111-2222-3333-444455556666"
    assert cc.command("p", sid, exe="x")[-2:] == ["--resume", sid]
    raises(cc.command, "p", "abc; rm -rf", contains="session_id")
    servers = cc.mcp_config()["mcpServers"]
    assert set(servers) == {"datae", "datae-sql"}
    assert all(Path(s["args"][0]).is_absolute() and Path(s["args"][0]).exists() for s in servers.values())
    assert not cc.WORKDIR.resolve().is_relative_to(ROOT), "chạy ngoài dự án: không nạp CLAUDE.md, settings của DataE"


def lines(*evs):
    return [json.dumps(e, ensure_ascii=False) + "\n" for e in evs]


INIT = {"type": "system", "subtype": "init", "session_id": "s1",
        "tools": ["mcp__datae__performance_summary", "mcp__datae-sql__execute_sql"],
        "mcp_servers": [{"name": "datae", "status": "connected"}, {"name": "datae-sql", "status": "connected"}]}


def test_doc_luong_su_kien():
    answer = ("MER 7 ngày là **1,98**.\n\n```report\n" + json.dumps(SPEC) + "\n```\n\n```report\n"
              + json.dumps(dict(SPEC, chart="line")) + "\n```")
    out = list(cc.events(lines(
        INIT,
        {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "MER "}}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "mcp__datae__performance_summary"}]}},
        {"type": "result", "subtype": "success", "is_error": False, "result": answer, "session_id": "s1"},
        {"type": "result", "subtype": "success", "result": "không đọc tới đây"})))
    assert [e["t"] for e in out] == ["session", "text", "tool", "done"]
    assert out[2]["name"] == "datae · performance_summary"
    assert out[3]["text"] == "MER 7 ngày là **1,98**." and out[3]["session"] == "s1"
    assert out[3]["reports"] == [SPEC, dict(SPEC, chart="line")] and out[3]["report_errors"] == []

    killed = []
    bad = dict(INIT, tools=["Bash", "Read", "mcp__datae__performance_summary"])
    out = list(cc.events(lines(bad, {"type": "result", "subtype": "success", "result": "x"}), on_tools=killed.append))
    assert [e["t"] for e in out] == ["error"] and killed == [["Bash", "Read"]], "có tool ngoài 2 server thì dừng"

    out = list(cc.events(lines(dict(INIT, mcp_servers=[{"name": "datae-sql", "status": "failed"}]),
                               {"type": "result", "subtype": "error_max_turns", "is_error": True, "result": None})))
    assert [e["t"] for e in out] == ["warn", "session", "error"]

    text, specs, errs = cc.split_reports("A\n```report\n{bad json\n```\nB")
    assert specs == [] and len(errs) == 1 and "```" not in text
    many = "\n".join(f"```report\n{json.dumps(SPEC)}\n```" for _ in range(5))
    text, specs, errs = cc.split_reports("X\n" + many)
    assert len(specs) == cc.MAX_CHARTS and errs and text == "X"


class FakeProc:
    def __init__(self, cmd, **kw):
        FakeProc.last = self
        self.cmd, self.kw, self.sent = cmd, kw, []
        self.stdin = SimpleNamespace(write=self.sent.append, close=lambda: None)
        self.stdout = iter(lines(INIT, {"type": "result", "subtype": "success", "result": "ok", "session_id": "s1"}))
        self.stderr = SimpleNamespace(read=lambda: "")

    def poll(self):
        return 0

    def kill(self):
        pass


def test_hoi_qua_stdin_va_khoa_1_cau():
    old = cc.subprocess.Popen, cc.claude_exe, cc.WORKDIR
    with tempfile.TemporaryDirectory() as tmp:
        try:
            cc.subprocess.Popen, cc.claude_exe, cc.WORKDIR = FakeProc, (lambda: "claude.exe"), Path(tmp)
            question = 'MER "7 ngày" & ROAS?'
            out = list(cc.ask(question, "datae-514203"))
            assert out[-1] == {"t": "done", "text": "ok", "reports": [], "report_errors": [], "session": "s1"}
            assert FakeProc.last.sent == [question] and question not in FakeProc.last.cmd, "câu hỏi đi qua stdin"
            assert FakeProc.last.kw["cwd"] == Path(tmp) and (Path(tmp) / "mcp.json").exists()
            gen = cc.ask("câu 1", "p")
            next(gen)                                  # câu 1 đang chạy
            assert list(cc.ask("câu 2", "p"))[0]["msg"].startswith("Claude đang trả lời"), "mỗi lần 1 câu"
            list(gen)
            assert list(cc.ask("  ", "p"))[0]["t"] == "error"
        finally:
            cc.subprocess.Popen, cc.claude_exe, cc.WORKDIR = old


def test_kiem_spec_va_sql():
    assert rp.check_spec(SPEC)["y"] == ["rev"] and rp.check_spec(dict(SPEC, y="rev"))["y"] == ["rev"]
    assert "x" not in rp.check_spec({"title": "Bảng", "chart": "table", "sql": "select 1"})
    raises(rp.check_spec, dict(SPEC, chart="pie"), contains="chart")
    raises(rp.check_spec, dict(SPEC, y=[]), contains="cột y")
    raises(rp.check_spec, dict(SPEC, x=None), contains="cột x")
    raises(rp.check_spec, dict(SPEC, title=""), contains="tiêu đề")
    raises(rp.check_spec, [1, 2])
    assert rp.check_sql_text(SPEC["sql"] + ";") == SPEC["sql"]
    assert rp.check_sql_text("with a as (select 1 x) select * from a")
    assert rp.check_sql_text("select 'drop table; update' as s, `create` from t -- delete")
    raises(rp.check_sql_text, "delete from `p.gold.fct_orders` where true", contains="SELECT")
    raises(rp.check_sql_text, "select 1; drop table `p.gold.fct_orders`", contains="1 câu")
    raises(rp.check_sql_text, "with x as (select 1) insert into t select * from x", contains="insert")
    raises(rp.check_sql_text, "select 1 /* */ ; select 2", contains="1 câu")


def fake_client(statement="SELECT", tables=(("datae-514203", "gold", "fct_orders"),), mb=10):
    job = SimpleNamespace(statement_type=statement, total_bytes_processed=mb * 1024 * 1024,
                          referenced_tables=[SimpleNamespace(project=p, dataset_id=d, table_id=t) for p, d, t in tables])
    return SimpleNamespace(project="datae-514203", query=lambda sql, job_config=None: job)


def test_dry_run_chan_bang_la():
    rp.check_sql_bq(fake_client(tables=[("datae-514203", "gold", "a"), ("datae-514203", "silver", "b")]), "select 1")
    raises(rp.check_sql_bq, fake_client(tables=[("datae-514203", "raw", "shopify_orders")]), "s", contains="raw")
    raises(rp.check_sql_bq, fake_client(tables=[("datae-514203", "pii", "customers")]), "s", contains="pii")
    raises(rp.check_sql_bq, fake_client(tables=[("bigquery-public-data", "gold", "x")]), "s", contains="bigquery-public-data")
    raises(rp.check_sql_bq, fake_client(statement="SCRIPT"), "s", contains="SCRIPT")
    raises(rp.check_sql_bq, fake_client(mb=80), "s", contains="50 MB")


def test_luu_xoa_va_route():
    from fastapi.testclient import TestClient

    from webapp.api import main

    old = rp.STORE, rp.run, main.client, main.version
    with tempfile.TemporaryDirectory() as tmp:
        try:
            rp.STORE = Path(tmp) / "reports.json"
            calls = []
            rp.run = lambda c, spec: calls.append(spec) or {"columns": ["tuan", "rev"], "rows": [{"tuan": "2026-11-08", "rev": 1.5}], "truncated": False}
            main.client = lambda: SimpleNamespace(project="datae-514203")
            main.version = lambda: "v1"
            c = TestClient(main.app)
            assert c.get("/api/reports").json() == {"reports": []}
            assert c.post("/api/reports/preview", json={"spec": SPEC}).json()["data"]["rows"][0]["rev"] == 1.5
            saved = c.post("/api/reports", json={"spec": SPEC}).json()
            assert saved["title"] == SPEC["title"] and len(saved["id"]) == 12
            assert [r["id"] for r in c.get("/api/reports").json()["reports"]] == [saved["id"]]
            n = len(calls)
            c.get(f"/api/reports/{saved['id']}/data")
            c.get(f"/api/reports/{saved['id']}/data")
            assert len(calls) == n + 1, "cùng phiên bản dữ liệu thì không chạy lại"
            main.version = lambda: "v2"
            c.get(f"/api/reports/{saved['id']}/data")
            assert len(calls) == n + 2, "có số mới thì chạy lại"
            assert c.delete(f"/api/reports/{saved['id']}").json() == {"ok": True}
            assert c.delete(f"/api/reports/{saved['id']}").status_code == 404
            assert c.get("/api/reports/khongco/data").status_code == 404
            rp.run = old[1]
            bad = c.post("/api/reports", json={"spec": dict(SPEC, sql="drop table `x.gold.y`")})
            assert bad.status_code == 400 and "SELECT" in bad.json()["detail"]
            assert c.get("/api/reports").json() == {"reports": []}, "SQL bị chặn thì không lưu"
        finally:
            rp.STORE, rp.run, main.client, main.version = old


def test_bai_phan_tich_ban_chup():
    from fastapi.testclient import TestClient

    from webapp.api import main

    old = rp.ANALYSES, rp.run, main.client, main.version, main.last_complete_day, main.fetch
    with tempfile.TemporaryDirectory() as tmp:
        try:
            rp.ANALYSES = Path(tmp) / "analyses.json"
            rows = [{"tuan": "2026-11-08", "rev": 44557.43}]
            rp.run = lambda c, spec: {"columns": ["tuan", "rev"], "rows": list(rows), "truncated": False}
            main.client = lambda: SimpleNamespace(project="datae-514203")
            main.version = lambda: "v1"
            from datetime import date

            import pandas as pd

            from dashboard import queries as q
            main.last_complete_day = lambda: date(2026, 11, 15)
            main.fetch = lambda sql, params: (pd.DataFrame([{"d": date(2026, 11, 15)}]) if sql == q.LATEST_LOADED
                                              else pd.DataFrame())
            c = TestClient(main.app)
            body = {"title": "Tuần 8–14/11", "text": "MER **1,98**. Nên giảm spend AirPods Case.",
                    "question": "Phân tích tuần trước", "specs": [SPEC]}
            saved = c.post("/api/analyses", json=body)
            assert saved.status_code == 200, saved.text
            a = saved.json()
            assert a["data_until"] == "2026-11-14", "ghi ngày trọn cuối của số lúc lưu"
            lst = c.get("/api/analyses").json()["analyses"]
            assert lst == [{"id": a["id"], "created": a["created"], "title": "Tuần 8–14/11", "data_until": "2026-11-14", "charts": 1}]
            rows[0]["rev"] = 1.0                      # số trong kho đổi sau khi lưu
            full = c.get(f"/api/analyses/{a['id']}").json()
            assert full["charts"][0]["data"]["rows"][0]["rev"] == 44557.43, "bản chụp giữ số lúc lưu"
            assert full["text"] == body["text"] and full["question"] == body["question"]
            assert c.post("/api/analyses", json=dict(body, specs=[SPEC] * 4)).status_code == 400
            assert c.post("/api/analyses", json=dict(body, title=" ")).status_code == 400
            assert c.post("/api/analyses", json=dict(body, specs=[dict(SPEC, chart="pie")])).status_code == 400
            assert len(c.get("/api/analyses").json()["analyses"]) == 1, "bài lỗi không được lưu"
            assert c.delete(f"/api/analyses/{a['id']}").json() == {"ok": True}
            assert c.get(f"/api/analyses/{a['id']}").status_code == 404
        finally:
            rp.ANALYSES, rp.run, main.client, main.version, main.last_complete_day, main.fetch = old


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"  ✓ {name}")
    print("PASS")
