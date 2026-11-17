"""Bridge synchronous read-only Claude events to ASGI with disconnect cancellation."""

import asyncio
import json
import queue
import threading


def response_events(request, produce):
    async def stream():
        stop = threading.Event()
        events = queue.Queue(maxsize=32)
        finished = object()

        def put(event):
            while not stop.is_set():
                try:
                    events.put(event, timeout=0.1)
                    return
                except queue.Full:
                    pass

        def worker():
            source = None
            try:
                source = produce(stop)
                for event in source:
                    if stop.is_set():
                        break
                    put(event)
            except Exception:
                put({"t": "error", "msg": "Luồng trả lời bị gián đoạn. Hãy thử lại."})
            finally:
                try:
                    if source is not None and hasattr(source, "close"):
                        source.close()
                finally:
                    put(finished)

        threading.Thread(target=worker, daemon=True, name="datae-chat-stream").start()
        try:
            while not stop.is_set():
                if await request.is_disconnected():
                    break
                try:
                    event = events.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.025)
                    continue
                if event is finished:
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            stop.set()

    return stream()
