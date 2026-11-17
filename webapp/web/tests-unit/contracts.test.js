import { test } from "node:test";
import assert from "node:assert/strict";
import { csvText, readExplore, exploreHash } from "../src/explore.js";
import { readEvents } from "../src/sse.js";
test("URL filters survive round trip and malformed values are bounded", () => {
  const state = {
    search: "Heron & Mây",
    filter: "Long Sleeve",
    sort: "units",
    desc: false,
    page: 2,
  };
  const hash = exploreHash("#products?preset=28", state);
  assert.match(hash, /preset=28/);
  assert.deepEqual(readExplore(hash, ["units"], "units"), state);
  assert.equal(
    readExplore("#products?p=-4&sort=secret", ["units"], "units").page,
    0,
  );
  assert.equal(readExplore("#products?p=NaN", ["units"], "units").page, 0);
  assert.equal(
    readExplore("#products?p=999999999", ["units"], "units").page,
    10000,
  );
});
test("CSV keeps numbers, zero and missing cells; quotes and formula-like text are escaped", () => {
  const rows = [
    { name: 'Heron, "blue"\nline', revenue: -12.5, units: 0, missing: null },
    { name: '  =HYPERLINK("x")', revenue: 2, units: 3 },
  ];
  const csv = csvText(
    rows,
    ["name", "revenue", "units", "missing"].map((key) => ({ key, label: key })),
  );
  assert.ok(csv.startsWith("\uFEFF"));
  assert.match(csv, /'  =HYPERLINK/);
  assert.ok(csv.includes('"-12.5","0",""'));
  assert.ok(csv.includes('Heron, ""blue""\nline'));
});
const response = (chunks) =>
  new Response(
    new ReadableStream({
      start(controller) {
        for (const c of chunks) controller.enqueue(c);
        controller.close();
      },
    }),
  );
const collect = async (res) => {
  const events = [];
  for await (const event of readEvents(res)) events.push(event);
  return events;
};
test("SSE handles split UTF-8, CRLF, multiline data, comments and multiple frames", async () => {
  const data =
    ': heartbeat\r\n\r\ndata: {"t":"text",\r\ndata: "s":"Hươu"}\r\n\r\ndata: {"t":"done"}\n\n';
  const bytes = new TextEncoder().encode(data);
  const chunks = Array.from(bytes, (b) => Uint8Array.of(b));
  assert.deepEqual(await collect(response(chunks)), [
    { t: "text", s: "Hươu" },
    { t: "done" },
  ]);
});
test("SSE surfaces broken JSON, truncated frames, outages and oversize data", async () => {
  for (const data of [
    "data: bad\n\n",
    'data: {"t":"text"}',
    "data: null\n\n",
    `data: ${"x".repeat(1000001)}`,
  ])
    await assert.rejects(() =>
      collect(response([new TextEncoder().encode(data)])),
    );
  await assert.rejects(
    () =>
      collect(
        new Response(JSON.stringify({ detail: "Mất kết nối" }), {
          status: 503,
        }),
      ),
    /Mất kết nối/,
  );
});
