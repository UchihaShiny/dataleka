import { useEffect, useRef, useState } from "react";
import { api, ReportChart } from "./report.jsx";
export default function ReportEditor({ initial, onSaved, onCancel, id }) {
  const [spec, setSpec] = useState(initial),
    [preview, setPreview] = useState(null),
    [error, setError] = useState(null),
    [busy, setBusy] = useState(false);
  const revision = useRef(0),
    pending = useRef(null),
    saving = useRef(false);
  const [phase, setPhase] = useState("");
  useEffect(
    () => () => {
      revision.current++;
      pending.current?.abort();
    },
    [],
  );
  const dirty = JSON.stringify(spec) !== JSON.stringify(initial);
  const cancel = () => {
    if (!dirty || window.confirm("Bỏ các thay đổi chưa lưu của biểu đồ?"))
      onCancel();
  };
  const change = (key, value) => {
    if (saving.current) return;
    revision.current++;
    pending.current?.abort();
    setBusy(false);
    setPhase("");
    setSpec((s) => ({ ...s, [key]: value }));
    setPreview(null);
    setError(null);
  };
  const run = async () => {
    const token = ++revision.current;
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    setPhase("preview");
    setPreview(null);
    setError(null);
    try {
      const result = await api("/api/reports/preview", {
        body: { spec },
        signal: controller.signal,
      });
      if (revision.current === token) setPreview(result);
    } catch (e) {
      if (revision.current === token && !controller.signal.aborted)
        setError(e.message);
    } finally {
      if (revision.current === token) {
        setBusy(false);
        setPhase("");
      }
    }
  };
  const save = async () => {
    if (saving.current || !preview) return;
    saving.current = true;
    setPhase("save");
    setBusy(true);
    setError(null);
    try {
      const r = await api(id ? `/api/reports/${id}` : "/api/reports", {
        method: id ? "PUT" : "POST",
        body: { spec: preview.spec },
      });
      onSaved(r);
    } catch (e) {
      setError(e.message);
    } finally {
      saving.current = false;
      setPhase("");
      setBusy(false);
    }
  };
  return (
    <div className="report-editor">
      {dirty && (
        <p className="cap" role="status">
          Thay đổi chưa lưu · sửa nội dung cần xem trước lại trước khi lưu.
        </p>
      )}
      <fieldset disabled={phase === "save"} className="editor-fields">
        <div className="toolbar">
          <label>
            Tiêu đề
            <input
              value={spec.title}
              maxLength={120}
              onChange={(e) => change("title", e.target.value)}
            />
          </label>
          <label>
            Loại biểu đồ
            <select
              value={spec.chart}
              onChange={(e) => change("chart", e.target.value)}
            >
              {["line", "bar", "table"].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
        </div>
        <label>
          SQL chỉ đọc
          <textarea
            rows={5}
            value={spec.sql}
            maxLength={8000}
            onChange={(e) => change("sql", e.target.value)}
          />
        </label>
        {spec.chart !== "table" && (
          <div className="toolbar">
            <label>
              Cột X
              <input
                value={spec.x || ""}
                onChange={(e) => change("x", e.target.value)}
              />
            </label>
            <label>
              Cột Y (cách nhau dấu phẩy)
              <input
                value={(spec.y || []).join(",")}
                onChange={(e) =>
                  change(
                    "y",
                    e.target.value
                      .split(",")
                      .map((v) => v.trim())
                      .filter(Boolean),
                  )
                }
              />
            </label>
          </div>
        )}
      </fieldset>
      <div className="row">
        <button
          className="btn ghost small"
          disabled={busy || !spec.title.trim()}
          onClick={run}
        >
          {phase === "preview" ? "Đang kiểm tra…" : "Xem trước"}
        </button>
        {preview && (
          <button className="btn" onClick={save} disabled={busy}>
            Lưu biểu đồ
          </button>
        )}
        <button
          className="btn ghost small"
          onClick={cancel}
          disabled={phase === "save"}
        >
          Hủy
        </button>
      </div>
      {error && (
        <div className="note err" role="alert">
          {error}
        </div>
      )}
      {preview && <ReportChart spec={preview.spec} data={preview.data} />}
    </div>
  );
}
