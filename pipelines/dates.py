"""Khoảng ngày và cache theo ngày dùng chung cho các nguồn kéo theo ngày (Meta, Klaviyo).

Ngày luôn theo America/Phoenix (UTC−7, không đổi giờ mùa hè). Chỉ nhận ngày đã kết thúc.
"""

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PHOENIX = timezone(timedelta(hours=-7))
MAX_DAYS_PER_RUN = 31
WORK_HOURS = (8, 17)  # giờ làm việc Phoenix = 22:00–07:00 giờ Việt Nam


def in_phoenix_work_hours(now: datetime | None = None) -> bool:
    hour = (now or datetime.now(PHOENIX)).astimezone(PHOENIX).hour
    return WORK_HOURS[0] <= hour < WORK_HOURS[1]


def guard_work_hours(force: bool, now: datetime | None = None) -> None:
    """Meta, Klaviyo dùng chung quota với đội vận hành; không chạy trong giờ họ làm việc."""
    if in_phoenix_work_hours(now) and not force:
        sys.exit("Đang trong giờ làm việc Phoenix (22:00–07:00 giờ Việt Nam). Quota API dùng chung với đội ads, "
                 "nên chưa chạy. Chạy lại sau 07:00, hoặc thêm --force nếu đã báo anh.")


FRESH_HOURS = 36  # brief: data mới trong vòng 36 giờ


def hours_behind(latest: date | datetime, now: datetime | None = None) -> float:
    """Số giờ từ thời điểm dữ liệu mới nhất đến bây giờ.

    Với cột ngày (Meta, Klaviyo), dữ liệu của một ngày coi như mới tới cuối ngày đó theo giờ Phoenix.
    """
    now = now or datetime.now(timezone.utc)
    if isinstance(latest, datetime):
        moment = latest if latest.tzinfo else latest.replace(tzinfo=timezone.utc)
    else:
        moment = datetime(latest.year, latest.month, latest.day, tzinfo=PHOENIX) + timedelta(days=1)
    return max(0.0, (now - moment).total_seconds() / 3600)


def last_complete_day(now: datetime | None = None) -> date:
    return (now or datetime.now(PHOENIX)).astimezone(PHOENIX).date() - timedelta(days=1)


def window(args, today_done: date) -> tuple[date, date]:
    """Đọc --since/--until; mặc định 7 ngày đã trọn gần nhất. Mỗi lần tối đa 31 ngày."""
    if args.since or args.until:
        if not (args.since and args.until):
            sys.exit("Cần truyền cả --since và --until")
        since, until = args.since, args.until
    else:
        until, since = today_done, today_done - timedelta(days=6)
    if since > until:
        sys.exit("--since phải trước hoặc bằng --until")
    if (until - since).days + 1 > MAX_DAYS_PER_RUN:
        sys.exit(f"Mỗi lần chạy tối đa {MAX_DAYS_PER_RUN} ngày để giữ quota. Nạp dần từng tháng bằng --since/--until.")
    if until > today_done:
        sys.exit(f"--until {until} chưa kết thúc theo giờ Phoenix; ngày đã trọn gần nhất là {today_done}")
    return since, until


def months(since: date, until: date):
    """Chia khoảng ngày thành từng tháng để mỗi lần gọi API không quá nặng."""
    start = since
    while start <= until:
        next_month = (start.replace(day=1) + timedelta(days=32)).replace(day=1)
        end = min(until, next_month - timedelta(days=1))
        yield start, end
        start = end + timedelta(days=1)


def weeks(since: date, until: date):
    """Chia tiếp từng tháng thành đoạn tối đa 7 ngày, không vắt qua 2 tháng."""
    for month_start, month_end in months(since, until):
        start = month_start
        while start <= month_end:
            end = min(month_end, start + timedelta(days=6))
            yield start, end
            start = end + timedelta(days=1)


def days(since: date, until: date) -> list[str]:
    return [(since + timedelta(days=i)).isoformat() for i in range((until - since).days + 1)]


def write_days(cache: Path, by_day: dict[str, list]) -> None:
    """Ghi đè file của từng ngày, kể cả ngày không có dòng nào, để biết ngày đó đã lấy rồi."""
    cache.mkdir(parents=True, exist_ok=True)
    for day, rows in by_day.items():
        (cache / f"{day}.json").write_text(json.dumps(rows, ensure_ascii=False, default=str), encoding="utf-8")


def read_days(cache: Path):
    for path in sorted(cache.glob("*.json")):
        yield from json.loads(path.read_text(encoding="utf-8"))


# Ngày đã trọn THEO LÚC NẠP (16/11): nạp lúc 00:07 Phoenix thì ngày hôm trước đã trọn dù ngày mới chưa có đơn.
# Trước đây đoán từ dữ liệu (max(order_date) − 1) nên nạp ngay sau nửa đêm Phoenix bị mất trọn 1 ngày.
# load_shopify ghi lúc BẮT ĐẦU kéo (đơn tạo trước lúc đó đều có trong lần kéo); pipelines.dbt đọc và truyền cho dbt.
LOAD_STATE = Path(__file__).resolve().parent.parent / "data" / "last_load.json"


def record_load(source: str, started: datetime, path: Path | None = None) -> date:
    path = path or LOAD_STATE
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    done = last_complete_day(started)
    state[source] = {"started_at": started.astimezone(timezone.utc).isoformat(timespec="seconds"),
                     "complete_through": str(done)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    return done


def loaded_complete_through(path: Path | None = None) -> date | None:
    """Ngày đã trọn của lần nạp Shopify thành công gần nhất trên máy này; chưa có thì None."""
    path = path or LOAD_STATE
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8")).get("shopify", {}).get("complete_through")
    return date.fromisoformat(value) if value else None
