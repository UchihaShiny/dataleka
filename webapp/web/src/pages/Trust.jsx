import { useEffect, useState } from "react";
import { api } from "../report.jsx";
import { Table, Sec } from "../ui.jsx";
import { dmy, vn } from "../format.js";
export default function Trust({ meta }) {
  const [data, setData] = useState(null),
    [error, setError] = useState(null),
    [query, setQuery] = useState(""),
    [retry, setRetry] = useState(0);
  useEffect(() => {
    let stop = false;
    setError(null);
    Promise.all([api("/api/health"), api("/api/definitions")])
      .then(([health, defs]) => !stop && setData({ health, defs }))
      .catch((e) => !stop && setError(e.message));
    return () => {
      stop = true;
    };
  }, [meta?.version, retry]);
  if (error)
    return (
      <div className="note err" role="alert">
        {error}{" "}
        <button className="btn ghost small" onClick={() => setRetry(retry + 1)}>
          Thử lại
        </button>
      </div>
    );
  if (!data)
    return (
      <div className="loading" role="status">
        Đang đọc bằng chứng dữ liệu…
      </div>
    );
  const { health, defs } = data;
  return (
    <>
      <div className="trust-intro">
        <span className="pv-tag">
          {meta?.mode === "demo" ? "Bằng chứng giả lập" : "Bằng chứng từ gold"}
        </span>
        <h2>Hiểu số trước khi quyết định.</h2>
        <p>
          Ngày kinh doanh America/Phoenix. Chỉ ngày đã trọn được đưa vào báo cáo
          theo kỳ. Dấu “–” nghĩa là chưa biết hoặc không có mẫu số.
        </p>
      </div>
      <Sec title="Coverage & độ mới" cap={health.note} />
      <Table
        rows={health.sources}
        cols={[
          { key: "source", label: "Nguồn" },
          {
            key: "first_date",
            label: "Ngày đầu có dòng",
            fmt: (v) => (v ? dmy(v) : "Chưa biết"),
          },
          {
            key: "last_date",
            label: "Ngày cuối có dòng",
            fmt: (v) => (v ? dmy(v) : "Chưa biết"),
          },
          {key: "days_behind_clock", label: "Trễ ngày so hôm qua Phoenix", num: true, fmt: v => vn(v,0)},
          {
            key: "observed_days",
            label: "Ngày có dòng",
            num: true,
            fmt: (v) => vn(v, 0),
          },
          {
            key: "calendar_days",
            label: "Ngày lịch trong khoảng",
            num: true,
            fmt: (v) => vn(v, 0),
          },
          {
            key: "verified_ingestion",
            label: "Đối soát nguồn",
            fmt: () => "Chưa có bằng chứng",
          },
        ]}
      />
      <div className="note">
        Ngày trọn theo kho:{" "}
        <b>{health.load?.complete_through || "Chưa biết"}</b> · phương pháp:{" "}
        {health.load?.method || "Chưa biết"}.<br />
        Dựng load_status: {health.load?.built_at || "Chưa biết"}. Không suy ra
        freshness từng nguồn từ thời gian sửa bảng.
      </div>
      <Sec
        title="Từ điển chỉ số"
        cap="Đọc trực tiếp transform/metrics.yml — cùng nguồn định nghĩa với MCP. Các lưu ý dưới đây là một phần của metric."
      />
      <label className="dictionary-search">
        Tìm chỉ số
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="MER, CLV, doanh thu…"
        />
      </label>
      <div className="dictionary">
        {Object.entries(defs.metrics || {})
          .filter(([key, m]) =>
            `${key} ${m.label}`.toLowerCase().includes(query.toLowerCase()),
          )
          .map(([key, m]) => (
            <details key={key}>
              <summary>
                <code>{key}</code>
                <b>{m.label}</b>
                <span>＋</span>
              </summary>
              <div>
                <p>
                  <b>Công thức:</b> {m.formula}
                </p>
                <p>
                  <b>Gộp kỳ:</b> {m.sum_rule}
                </p>
                <p>
                  <b>Nguồn:</b> {m.source} · {m.grain}
                </p>
                <ul>
                  {m.traps.map((t, i) => (
                    <li key={i}>{t}</li>
                  ))}
                </ul>
              </div>
            </details>
          ))}
      </div>
    </>
  );
}
