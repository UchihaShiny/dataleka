"""Khám phá schema Klaviyo trên 1 ngày mẫu. Chỉ đọc, không ghi BigQuery, không lấy event thô (có email).

Klaviyo theo chuẩn JSON:API: mỗi bản ghi trả đủ `attributes` và `relationships`, nên mẫu thật cũng chính là
schema (bước 1 và 2 gộp làm một, không cần tải OpenAPI spec). Lấy nguyên phản hồi:
campaigns (kèm campaign-messages), flows, flow-actions và flow-messages của 3 flow đầu, metrics, và
Placed Order của ngày mẫu nhóm theo message và theo flow (để thấy các chiều nhóm có thể dùng).

Khoảng 10–15 lần gọi, giãn nhịp như pipeline.
Chạy từ thư mục gốc:  python checks/explore_klaviyo.py [--day 2026-11-07]
Sau đó:  python checks/profile_sample.py klaviyo
"""

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "checks"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from pipelines.sources import klaviyo  # noqa: E402
from profile_sample import save  # noqa: E402

FLOWS_SAMPLED = 3


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", type=date.fromisoformat, default=date(2026, 11, 7))
    args = parser.parse_args()

    print("== Klaviyo: bản ghi JSON:API đủ trường ==")
    campaigns, included = klaviyo.get_all("/campaigns", {"include": "campaign-messages"})
    save("klaviyo", "campaigns", campaigns)
    save("klaviyo", "campaign_messages", [i for i in included if i.get("type") == "campaign-message"])

    flows, _ = klaviyo.get_all("/flows")
    save("klaviyo", "flows", flows)
    actions, messages = [], []
    for flow in flows[:FLOWS_SAMPLED]:
        got, _ = klaviyo.get_all(f"/flows/{flow['id']}/flow-actions")
        actions.extend({"flow_id": flow["id"], **a} for a in got)
    for action in actions:
        got, _ = klaviyo.get_all(f"/flow-actions/{action['id']}/flow-messages")
        messages.extend({"flow_action_id": action["id"], **m} for m in got)
    save("klaviyo", "flow_actions", actions)
    save("klaviyo", "flow_messages", messages)

    metrics, _ = klaviyo.get_all("/metrics")
    save("klaviyo", "metrics", metrics)

    placed = next((m for m in metrics if (m.get("attributes") or {}).get("name") == "Placed Order"), None)
    if placed:
        for by in ("$attributed_message", "$attributed_flow"):
            dates, groups = klaviyo.aggregate(placed["id"], by, args.day, args.day, with_value=True)
            save("klaviyo", f"placed_order_theo_{by.strip('$')}", [{"dates": dates, **g} for g in groups])
    else:
        print("  không thấy metric Placed Order")
    klaviyo.tracker.save(check="explore", day=args.day)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
