"""Theo dõi mức dùng quota API trong một lần chạy và ghi sổ logs/limits.jsonl.

Mỗi nguồn tạo một Tracker, gọi tracker.call() trước mỗi request (để giãn nhịp), tracker.seen(pct)
khi đọc được mức dùng, tracker.waited(giây) khi phải chờ. Cuối lần chạy gọi tracker.save().
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LOGS = Path(__file__).resolve().parent.parent / "logs"


def logs_dir() -> Path:
    logs = Path(os.environ.get("DATAE_LOGS") or DEFAULT_LOGS)  # test đặt thư mục tạm
    logs.mkdir(parents=True, exist_ok=True)
    return logs


class Tracker:
    def __init__(self, source: str, min_interval: float = 0.0):
        self.source = source
        self.min_interval = min_interval
        self.calls = 0
        self.peak_pct = 0.0
        self.waits = 0
        self.wait_seconds = 0.0
        self._last = None
        self.started = datetime.now(timezone.utc)

    def call(self) -> None:
        """Giãn nhịp: chờ cho đủ min_interval kể từ lần gọi trước."""
        if self._last is not None and self.min_interval:
            gap = time.monotonic() - self._last
            if gap < self.min_interval:
                time.sleep(self.min_interval - gap)
        self._last = time.monotonic()
        self.calls += 1

    def seen(self, pct: float) -> None:
        self.peak_pct = max(self.peak_pct, pct)

    def waited(self, seconds: float) -> None:
        self.waits += 1
        self.wait_seconds += seconds

    def summary(self) -> str:
        return (f"{self.source}: {self.calls} lần gọi, mức dùng cao nhất {self.peak_pct:.0f}%, "
                f"chờ {self.waits} lần ({self.wait_seconds:.0f} giây)")

    def event(self, **fields) -> None:
        """Ghi một sự kiện (ví dụ bị chặn kèm header mức dùng) vào sổ, không in, không tính là một lần chạy."""
        record = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source": self.source,
                  "event": True, **fields}
        with (logs_dir() / "limits.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def save(self, **extra) -> None:
        logs = logs_dir()
        record = {
            "at": self.started.isoformat(timespec="seconds"), "source": self.source, "calls": self.calls,
            "peak_pct": round(self.peak_pct, 1), "waits": self.waits, "wait_seconds": round(self.wait_seconds),
            **{k: str(v) for k, v in extra.items()},
        }
        with (logs / "limits.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(self.summary())
