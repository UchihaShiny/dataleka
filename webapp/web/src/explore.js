// Shareable aggregate exploration state. URL is the source of truth; no data is stored here.
export function readExplore(hash, columns, fallback) {
  const params = new URLSearchParams(hash.split("?")[1] || "");
  const raw = Number(params.get("p") || 1);
  return {
    search: (params.get("q") || "").slice(0, 200),
    filter: (params.get("line") || "").slice(0, 200),
    sort: columns.includes(params.get("sort")) ? params.get("sort") : fallback,
    desc: params.get("dir") !== "asc",
    page: Number.isSafeInteger(raw) && raw > 0 ? Math.min(raw - 1, 10000) : 0,
  };
}
export function exploreHash(hash, state) {
  const [page, qs] = hash.split("?");
  const params = new URLSearchParams(qs || "");
  for (const [key, value] of Object.entries({
    q: state.search,
    line: state.filter,
    sort: state.sort,
    dir: state.desc ? "desc" : "asc",
    p: state.page ? String(state.page + 1) : "",
  })) {
    if (value) params.set(key, value);
    else params.delete(key);
  }
  return `${page}?${params}`;
}
export function csvText(rows, cols) {
  const quote = (value) => {
    let text = value == null ? "" : String(value);
    // Protect string cells from spreadsheet formulas; signed numeric values stay numeric.
    if (typeof value === "string" && /^[\s]*[=+@\-]|^[\t\r\n]/.test(text))
      text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  };
  return (
    "\uFEFF" +
    [
      cols.map((c) => quote(c.label)).join(","),
      ...rows.map((r) => cols.map((c) => quote(r[c.key])).join(",")),
    ].join("\r\n")
  );
}
