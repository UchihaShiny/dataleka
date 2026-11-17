import { useMemo, useRef, useState, useEffect } from "react";
import { Table } from "./ui.jsx";
import { readExplore, exploreHash, csvText } from "./explore.js";

export default function Explorer({
  rows,
  cols,
  title,
  nameKey,
  filterKey,
  truncated = false,
}) {
  const keys = cols.map((c) => c.key),
    fallback = cols.find((c) => c.num)?.key || nameKey;
  const [selection, setSelection] = useState(() =>
    readExplore(window.location.hash, keys, fallback),
  );
  const { search, filter, sort, desc } = selection;
  useEffect(() => {
    const restore = () =>
      setSelection(readExplore(window.location.hash, keys, fallback));
    window.addEventListener("hashchange", restore);
    return () => window.removeEventListener("hashchange", restore);
  }, [keys.join("|"), fallback]);
  const update = (patch) => {
    const next = { ...selection, page: 0, ...patch };
    setSelection(next);
    // Replace while typing so back/forward still follows page and period navigation.
    history.replaceState(null, "", exploreHash(window.location.hash, next));
  };
  const [detail, setDetail] = useState(null),
    dialog = useRef(null);
  const filtered = useMemo(
    () =>
      rows
        .filter(
          (r) =>
            (!filter || r[filterKey] === filter) &&
            String(r[nameKey] || "")
              .toLocaleLowerCase("vi")
              .includes(search.toLocaleLowerCase("vi")),
        )
        .sort((a, b) => {
          const x = a[sort],
            y = b[sort];
          if (x == null && y == null) return 0;
          if (x == null) return 1;
          if (y == null) return -1;
          return (
            (typeof x === "number"
              ? x - y
              : String(x).localeCompare(String(y), "vi")) * (desc ? -1 : 1)
          );
        }),
    [rows, search, filter, sort, desc, nameKey, filterKey],
  );
  const lastPage = Math.max(0, Math.ceil(filtered.length / 10) - 1);
  const page = Math.min(selection.page, lastPage);
  const setPage = (choose) => update({ page: choose(page) });
  useEffect(() => {
    if (selection.page !== page) {
      const next = { ...selection, page };
      setSelection(next);
      history.replaceState(null, "", exploreHash(window.location.hash, next));
    }
  }, [page, selection.page]);
  useEffect(() => {
    if (detail) dialog.current?.showModal();
  }, [detail]);
  const exportCsv = () => {
    const url = URL.createObjectURL(
      new Blob([csvText(filtered, cols)], { type: "text/csv;charset=utf-8" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "deerlys-aggregate.csv";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return (
    <section className="explorer">
      <div className="explore-head">
        <div>
          <span className="eyebrow">KHÁM PHÁ DỮ LIỆU</span>
          <h3>{title}</h3>
        </div>
        <button
          className="btn ghost small"
          onClick={exportCsv}
          disabled={!filtered.length}
        >
          ↓ Xuất CSV tổng hợp
        </button>
      </div>
      <div className="toolbar">
        <label>
          Tìm kiếm
          <input
            type="search"
            maxLength={200}
            value={search}
            onChange={(e) => update({ search: e.target.value })}
            placeholder="Tìm theo tên…"
          />
        </label>
        <label>
          Dòng sản phẩm
          <select
            value={filter}
            onChange={(e) => update({ filter: e.target.value })}
          >
            <option value="">Tất cả</option>
            {[...new Set(rows.map((r) => r[filterKey]).filter(Boolean))]
              .sort()
              .map((v) => (
                <option key={v}>{v}</option>
              ))}
          </select>
        </label>
        <label>
          Sắp xếp
          <select
            value={sort}
            onChange={(e) => update({ sort: e.target.value })}
          >
            {cols.map((c) => (
              <option key={c.key} value={c.key}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <button
          className="btn ghost small"
          onClick={() => update({ desc: !desc })}
          aria-label={
            desc ? "Giảm dần, đổi chiều sắp xếp" : "Tăng dần, đổi chiều sắp xếp"
          }
        >
          {desc ? "↓ Giảm dần" : "↑ Tăng dần"}
        </button>
      </div>
      {(search || filter) && (
        <button
          className="btn ghost small"
          onClick={() => update({ search: "", filter: "" })}
        >
          Xóa bộ lọc
        </button>
      )}
      <p className="cap" role="status">
        {filtered.length} / {rows.length} dòng tổng hợp · Bấm tên để xem chi
        tiết. CSV theo bộ lọc hiện tại, USD.
        {truncated &&
          " Giới hạn 1.000 dòng đầu theo doanh thu/spend; CSV không bao gồm phần ngoài giới hạn."}
      </p>
      <Table
        rows={filtered.slice(page * 10, page * 10 + 10)}
        cols={cols.map((c) =>
          c.key === nameKey
            ? {
                ...c,
                fmt: (v, r) => (
                  <button className="text-link" onClick={() => setDetail(r)}>
                    {v}
                  </button>
                ),
              }
            : c,
        )}
      />
      {filtered.length > 10 && (
        <div className="pagination">
          <span>
            Trang {page + 1}/{Math.ceil(filtered.length / 10)} · CSV gồm tất cả
            dòng khớp bộ lọc
          </span>
          <button
            className="btn ghost small"
            onClick={() => setPage((p) => p - 1)}
            disabled={page === 0}
          >
            Trước
          </button>
          <button
            className="btn ghost small"
            onClick={() => setPage((p) => p + 1)}
            disabled={(page + 1) * 10 >= filtered.length}
          >
            Tiếp
          </button>
        </div>
      )}
      {!filtered.length && (
        <div className="empty">
          Không có kết quả. Thử từ khóa hoặc bộ lọc khác.
        </div>
      )}
      <dialog
        ref={dialog}
        onClose={() => setDetail(null)}
        aria-labelledby={`detail-${nameKey}`}
      >
        <div className="pv-head">
          <h3 id={`detail-${nameKey}`}>{detail?.[nameKey]}</h3>
          <button
            className="btn ghost small"
            onClick={() => dialog.current.close()}
            autoFocus
          >
            Đóng
          </button>
        </div>
        <p className="cap">
          Tổng hợp trong kỳ đang chọn · không có thông tin khách hàng.
        </p>
        <dl>
          {detail &&
            cols.map((c) => (
              <div key={c.key}>
                <dt>{c.label}</dt>
                <dd>
                  {c.fmt
                    ? c.fmt(detail[c.key], detail)
                    : (detail[c.key] ?? "Chưa biết")}
                </dd>
              </div>
            ))}
        </dl>
      </dialog>
    </section>
  );
}
