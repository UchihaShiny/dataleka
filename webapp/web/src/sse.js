// Read SSE incrementally, including UTF-8 split across chunks and CRLF framing.
export async function* readEvents(response) {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Lỗi ${response.status}`);
  }
  if (!response.body) throw new Error("Không nhận được luồng trả lời.");
  const reader = response.body.getReader(),
    decoder = new TextDecoder();
  let pending = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      pending += decoder.decode(value, { stream: !done });
      if (pending.length > 1_000_000)
        throw new Error("Luồng trả lời vượt giới hạn kích thước.");
      let match;
      while ((match = /\r?\n\r?\n/.exec(pending))) {
        const frame = pending.slice(0, match.index);
        pending = pending.slice(match.index + match[0].length);
        const data = frame
          .split(/\r?\n/)
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).replace(/^ /, ""))
          .join("\n");
        if (data) {
          let event;
          try {
            event = JSON.parse(data);
          } catch {
            throw new Error("Phản hồi không đúng định dạng. Hãy thử lại.");
          }
          if (
            !event ||
            typeof event !== "object" ||
            typeof event.t !== "string"
          )
            throw new Error("Sự kiện trả lời không hợp lệ.");
          yield event;
        }
      }
      if (done) break;
    }
    if (pending.trim() && !pending.trim().startsWith(":"))
      throw new Error("Kết nối dừng giữa một sự kiện. Hãy thử lại.");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
