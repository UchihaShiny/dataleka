"""Kiểm tính độ mới theo giờ Phoenix (brief: data mới trong vòng 36 giờ). Không gọi mạng.

Chạy từ thư mục gốc:  python tests/test_dates.py
"""

import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from pipelines.dates import FRESH_HOURS, hours_behind, last_complete_day  # noqa: E402

now = datetime(2026, 11, 9, 8, 0, tzinfo=timezone.utc)  # 1:00 sáng 9/11 giờ Phoenix
assert hours_behind(date(2026, 11, 8), now) == 1.0  # ngày 8/11 kết thúc lúc 07:00 UTC 9/11
assert hours_behind(date(2026, 11, 7), now) == 25.0
assert hours_behind(date(2026, 11, 6), now) == 49.0 > FRESH_HOURS
assert hours_behind(datetime(2026, 11, 9, 9, 0, tzinfo=timezone.utc), now) == 0.0
assert last_complete_day(now) == date(2026, 11, 8)
assert last_complete_day(datetime(2026, 11, 9, 6, 59, tzinfo=timezone.utc)) == date(2026, 11, 7)

# Ngày đã trọn THEO LÚC NẠP (16/11): nạp 07:07 UTC = 00:07 Phoenix 16/11 → 15/11, dù ngày 16 chưa có đơn
import json  # noqa: E402
import tempfile  # noqa: E402

from pipelines.dates import loaded_complete_through, record_load  # noqa: E402
from pipelines.dbt import with_complete_through  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    state = Path(tmp) / "data" / "last_load.json"
    assert loaded_complete_through(state) is None, "chưa nạp lần nào"
    assert record_load("shopify", datetime(2026, 11, 16, 7, 7, 36, tzinfo=timezone.utc), state) == date(2026, 11, 15)
    assert loaded_complete_through(state) == date(2026, 11, 15)
    # nạp sáng VN như lịch cũ: 01:00 UTC 16/11 = 18:00 Phoenix 15/11 → 15/11 còn dở, trọn tới 14/11
    record_load("shopify", datetime(2026, 11, 16, 1, 0, tzinfo=timezone.utc), state)
    assert loaded_complete_through(state) == date(2026, 11, 14)
    record_load("meta", datetime(2026, 11, 16, 9, 0, tzinfo=timezone.utc), state)
    assert loaded_complete_through(state) == date(2026, 11, 14), "chỉ đọc mốc của Shopify"
    assert json.loads(state.read_text(encoding="utf-8"))["shopify"]["started_at"] == "2026-11-16T01:00:00+00:00"

# pipelines.dbt tự thêm --vars cho lệnh dựng model, không đụng lệnh khác hay --vars người gọi tự truyền
assert with_complete_through(["build"], date(2026, 11, 15)) == ["build", "--vars", '{"complete_through": "2026-11-15"}']
assert with_complete_through(["run", "-s", "load_status"], date(2026, 11, 15))[-1] == '{"complete_through": "2026-11-15"}'
assert with_complete_through(["debug"], date(2026, 11, 15)) == ["debug"]
assert with_complete_through(["build", "--vars", "{}"], date(2026, 11, 15)) == ["build", "--vars", "{}"]
print("PASS: độ mới theo giờ Phoenix, ngày đã trọn, ngày trọn theo lúc nạp, dbt nhận --vars")
