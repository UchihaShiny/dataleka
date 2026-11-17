// Hỏi Claude ngay trên dashboard. Backend gọi Claude Code (gói Max) chỉ với 2 server MCP chỉ đọc.
// Claude muốn vẽ thì trả spec báo cáo; trang tự chạy xem trước, Huy Anh bấm Lưu mới lưu.
import { useEffect, useRef, useState } from "react";
import { Markdown } from "../md.jsx";
import { api, ReportChart } from "../report.jsx";
import { readEvents } from "../sse.js";

const storageKey = (mode) =>
  mode === "demo" ? "datae-chat-demo" : "datae-chat";
// tải lại trang giữa lúc đang chạy xem trước: bỏ trạng thái "đang chạy" để chạy lại
const load = (KEY) => {
  try {
    const c = JSON.parse(sessionStorage.getItem(KEY)) || {
      msgs: [],
      session: null,
    };
    const fix = (pv) =>
      Object.fromEntries(
        Object.entries(pv || {})
          .filter(([, v]) => !v.loading)
          .map(([key, value]) => [
            key,
            value.saving
              ? {
                  ...value,
                  saving: false,
                  saveError:
                    "Lần lưu trước bị gián đoạn. Mở Báo cáo của tôi để kiểm tra trước khi lưu lại.",
                }
              : value,
          ]),
      );
    return {
      ...c,
      msgs: c.msgs.map((m) => ({
        ...m,
        previews: fix(m.previews),
        analysis: m.analysis?.saving ? undefined : m.analysis,
        ...(m.pending
          ? {
              pending: false,
              error: "Phiên trước đã bị ngắt. Bạn có thể gửi lại câu hỏi.",
            }
          : {}),
      })),
    };
  } catch {
    return { msgs: [], session: null };
  }
};
const store = (v, KEY) => {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(v));
  } catch {
    /* không lưu được thì thôi */
  }
};
const live = (t) => {
  const i = t.indexOf("```report");
  return i >= 0 ? t.slice(0, i) : t;
}; // giấu khối report khi đang gõ

const EXAMPLES = [
  "Phân tích tuần trước: MER, type đang lỗ, việc nên làm",
  "Dự báo đơn 14 ngày tới, có kịp BFCM không?",
  "Vẽ doanh thu theo product type 8 tuần gần nhất, cột chồng",
];

async function* sse(body, signal) {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  yield* readEvents(response);
}

function Preview({ spec, state = {}, update }) {
  const [retry, setRetry] = useState(0),
    saving = useRef(false);
  useEffect(() => {
    if (state.spec || (state.error && !retry)) return;
    const controller = new AbortController();
    update({ loading: true });
    api("/api/reports/preview", { body: { spec }, signal: controller.signal })
      .then(
        (p) =>
          !controller.signal.aborted && update({ spec: p.spec, data: p.data }),
      )
      .catch((e) => !controller.signal.aborted && update({ error: e.message }));
    return () => controller.abort();
  }, [spec, retry]);
  const save = async () => {
    if (saving.current) return;
    saving.current = true;
    update({ ...state, saving: true, saveError: null });
    try {
      await api("/api/reports", { body: { spec: state.spec } });
      update({ ...state, saving: false, saved: true });
    } catch (e) {
      update({ ...state, saving: false, saveError: e.message });
    } finally {
      saving.current = false;
    }
  };
  return (
    <div className="preview">
      <div className="pv-head">
        <b>{spec.title}</b>
        <span className="pv-tag">Xem trước</span>
      </div>
      {state.loading && <div className="loading">Đang chạy câu SQL…</div>}
      {state.error && (
        <div className="note err" role="alert">
          Không chạy được biểu đồ: {state.error}{" "}
          <button
            className="btn ghost small"
            onClick={() => setRetry((v) => v + 1)}
          >
            Thử lại biểu đồ
          </button>
        </div>
      )}
      {state.data && (
        <>
          <p className="cap">{state.spec.note}</p>
          <ReportChart spec={state.spec} data={state.data} />
          <details className="sql">
            <summary>Xem SQL</summary>
            <pre>
              <code>{state.spec.sql}</code>
            </pre>
          </details>
          <div className="row">
            {state.saved ? (
              <span className="ok">
                Đã lưu vào Biểu đồ của tôi (tự cập nhật).
              </span>
            ) : (
              <button
                className="btn ghost small"
                disabled={state.saving}
                onClick={save}
              >
                {state.saving ? "Đang lưu…" : "Lưu biểu đồ (tự cập nhật)"}
              </button>
            )}
            {state.saveError && (
              <span className="lose" role="alert">
                {state.saveError}
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// Lưu cả câu trả lời thành bài phân tích: bản chụp cố định (chữ + biểu đồ kèm số lúc lưu).
function SaveAnalysis({ msg, question, update }) {
  const [title, setTitle] = useState(question.slice(0, 120)),
    [open, setOpen] = useState(false);
  const inFlight = useRef(false);
  const s = msg.analysis || {};
  const charts = (msg.reports || []).filter((_, i) => msg.previews?.[i]?.spec);
  const pending = (msg.reports || []).some((_, i) => !msg.previews?.[i]?.spec);
  const save = () => {
    if (inFlight.current || pending) return;
    inFlight.current = true;
    update({ analysis: { saving: true } });
    api("/api/analyses", {
      body: { title: title.trim(), text: msg.text, question, specs: charts },
    })
      .then((a) => update({ analysis: { saved: a.title } }))
      .catch((e) => update({ analysis: { error: e.message } }))
      .finally(() => {
        inFlight.current = false;
      });
  };
  if (s.saved)
    return (
      <div className="row ok" role="status">
        Đã lưu bài “{s.saved}” vào Báo cáo của tôi.
      </div>
    );
  return (
    <div className="row">
      {open ? (
        <>
          <label>
            Tên bản chụp
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={160}
            />
          </label>
          <button
            className="btn"
            onClick={save}
            disabled={s.saving || pending || !title.trim()}
          >
            {s.saving ? "Đang lưu…" : "Lưu bản chụp"}
          </button>
          <p className="cap">
            {pending &&
              "Cần xem trước thành công tất cả biểu đồ trước khi lưu. "}
            Lưu chữ và số tại lúc bấm lưu, không tự cập nhật. Các biểu đồ được
            đọc lại một lần khi lưu.
          </p>
        </>
      ) : (
        <button className="btn" onClick={() => setOpen(true)}>
          Lưu bài phân tích
          {charts.length ? ` (kèm ${charts.length} biểu đồ)` : ""}
        </button>
      )}
      {s.error && (
        <span className="lose" role="alert">
          {s.error}
        </span>
      )}
    </div>
  );
}

export default function Ask({ meta }) {
  if (!meta)
    return <div className="loading">Đang xác định chế độ dữ liệu…</div>;
  return <Chat key={meta.mode} mode={meta.mode} />;
}
function Chat({ mode }) {
  const active = useRef(null);
  useEffect(() => () => active.current?.abort(), []);

  const [chat, setChat] = useState(() => load(storageKey(mode)));
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!busy) return;
    setElapsed(0);
    const id = setInterval(() => setElapsed((v) => v + 1), 1000);
    return () => clearInterval(id);
  }, [busy]);
  const end = useRef(null);
  useEffect(() => {
    store(chat, storageKey(mode));
  }, [chat]);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [chat.msgs.length, busy]);

  const patch = (idx, p) =>
    setChat((c) => ({
      ...c,
      msgs: c.msgs.map((m, i) => (i === idx ? { ...m, ...p } : m)),
    }));

  async function send(text) {
    text = text.trim();
    if (!text || busy) return;
    if (active.current) return;
    const controller = new AbortController();
    active.current = controller;
    setInput("");
    setBusy(true);
    const idx = chat.msgs.length + 1;
    setChat((c) => ({
      ...c,
      msgs: [
        ...c.msgs,
        { role: "user", text },
        { role: "claude", text: "", tools: [], pending: true },
      ],
    }));
    let terminal = false;
    let session = chat.session;
    try {
      for await (const ev of sse(
        { message: text, session },
        controller.signal,
      )) {
        if (ev.t === "session") {
          session = ev.id;
          setChat((c) => ({ ...c, session }));
        } else if (ev.t === "text")
          setChat((c) => ({
            ...c,
            msgs: c.msgs.map((m, i) =>
              i === idx ? { ...m, text: m.text + ev.s } : m,
            ),
          }));
        else if (ev.t === "tool")
          setChat((c) => ({
            ...c,
            msgs: c.msgs.map((m, i) =>
              i === idx ? { ...m, tools: [...m.tools, ev.name] } : m,
            ),
          }));
        else if (ev.t === "warn") patch(idx, { warn: ev.msg });
        else if (ev.t === "error") {
          terminal = true;
          patch(idx, { error: ev.msg, pending: false });
        } else if (ev.t === "done") {
          terminal = true;
          patch(idx, {
            text: ev.text,
            reports: ev.reports,
            report_errors: ev.report_errors,
            done: true,
            pending: false,
          });
          if (ev.session) setChat((c) => ({ ...c, session: ev.session }));
        }
      }
      if (!terminal)
        patch(idx, {
          error: "Kết nối dừng trước khi hoàn tất. Hãy gửi lại câu hỏi.",
          pending: false,
        });
    } catch (e) {
      patch(idx, {
        pending: false,
        error: controller.signal.aborted
          ? "Đã dừng trả lời. Bạn có thể gửi lại câu hỏi."
          : e.message,
      });
    } finally {
      active.current = null;
      setBusy(false);
    }
  }

  return (
    <div className="chat">
      <div className="cap">
        {mode === "demo" && (
          <p className="demo-banner">
            Demo: phản hồi phân tích mẫu cố định, không gọi Claude và không trả
            lời câu hỏi tùy ý.
          </p>
        )}
        Claude đọc kho bằng khoá chỉ đọc (15 tool <b>datae</b> + SQL tự viết qua{" "}
        <b>datae-sql</b>), không có quyền đọc file hay chạy lệnh. Nhờ phân tích,
        dự báo hay "vẽ…" đều được. Câu trả lời nào muốn giữ thì bấm{" "}
        <b>Lưu bài phân tích</b> (bản chụp cố định, xem lại ở Báo cáo của tôi).
        Chạy bằng tài khoản Claude của máy này.
      </div>
      {chat.msgs.length === 0 && (
        <div className="examples">
          {EXAMPLES.map((e) => (
            <button key={e} className="chip" onClick={() => send(e)}>
              {e}
            </button>
          ))}
        </div>
      )}
      {chat.msgs.map((m, i) =>
        m.role === "user" ? (
          <div key={i} className="msg user">
            {m.text}
          </div>
        ) : (
          <div key={i} className="msg claude">
            {m.tools?.length > 0 && (
              <div className="tools">
                {m.tools.map((t, k) => (
                  <span key={k} className="tool">
                    {t}
                  </span>
                ))}
              </div>
            )}
            {m.text ? (
              <Markdown text={live(m.text)} />
            ) : (
              !m.error &&
              busy &&
              i === chat.msgs.length - 1 && (
                <div className="loading">Claude đang xem số…</div>
              )
            )}
            {m.warn && <div className="note">{m.warn}</div>}
            {m.error && (
              <div className="note err" role="alert">
                {m.error}
              </div>
            )}
            {m.error && !busy && (
              <button
                className="btn ghost small"
                onClick={() => send(chat.msgs[i - 1]?.text || "")}
              >
                Gửi lại câu hỏi
              </button>
            )}
            {m.report_errors?.map((e, k) => (
              <div key={k} className="note err">
                {e}
              </div>
            ))}
            {m.reports?.map((spec, k) => (
              <Preview
                key={k}
                spec={spec}
                state={m.previews?.[k]}
                update={(p) =>
                  setChat((c) => ({
                    ...c,
                    msgs: c.msgs.map((x, j) =>
                      j === i
                        ? { ...x, previews: { ...x.previews, [k]: p } }
                        : x,
                    ),
                  }))
                }
              />
            ))}
            {m.done && m.text && (
              <SaveAnalysis
                msg={m}
                question={chat.msgs[i - 1]?.text || ""}
                update={(p) => patch(i, p)}
              />
            )}
          </div>
        ),
      )}
      {busy && (
        <div className="chat-progress">
          Đang đọc dữ liệu và chuẩn bị câu trả lời ·{" "}
          <span aria-live="off">{elapsed} giây</span>. Bạn có thể dừng bên dưới.
        </div>
      )}
      <form
        className="ask"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <textarea
          aria-label="Câu hỏi cho Claude"
          maxLength={4000}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={2}
          placeholder="Hỏi về số liệu… (Enter để gửi, Shift+Enter xuống dòng)"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
          disabled={busy}
        />
        <div className="ask-btns">
          <button
            className="btn"
            type="submit"
            disabled={busy || !input.trim()}
          >
            {busy ? "Đang trả lời…" : "Gửi"}
          </button>
          {busy && (
            <button
              className="btn ghost"
              type="button"
              onClick={() => active.current?.abort()}
            >
              Dừng trả lời
            </button>
          )}
          <button
            className="btn ghost"
            type="button"
            disabled={busy || !chat.msgs.length}
            onClick={() => setChat({ msgs: [], session: null })}
          >
            Cuộc mới
          </button>
        </div>
      </form>
      <div ref={end} />
    </div>
  );
}
