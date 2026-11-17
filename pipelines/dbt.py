"""Chạy dbt cho DataE từ bất kỳ thư mục nào.

Vì sao cần file này:
- dbt.exe bị Windows Application Control chặn, nên gọi dbt qua Python (dbt.cli.main).
- dbt đọc profiles.yml và model theo thư mục hiện tại: chạy sai chỗ là dbt không thấy model. File này luôn
  trỏ đúng transform/.
- Khoá GCP trong .env là đường dẫn tương đối (secrets/...). File này đổi sang đường dẫn tuyệt đối
  (DATAE_KEYFILE) để dbt tìm thấy dù chạy từ đâu.

Chạy từ thư mục gốc:
  python -m pipelines.dbt debug     # kiểm kết nối BigQuery, chưa tạo gì
  python -m pipelines.dbt build     # tạo view/table và chạy test
  python -m pipelines.dbt <lệnh dbt bất kỳ>
"""

import json
import os
import sys
from pathlib import Path

from pipelines.bq import settings
from pipelines.dates import loaded_complete_through

ROOT = Path(__file__).resolve().parent.parent
TRANSFORM = ROOT / "transform"
NEEDS_VARS = {"build", "run", "test", "compile"}


def with_complete_through(args: list[str], done=None) -> list[str]:
    """Thêm --vars complete_through (ngày đã trọn theo lúc nạp Shopify gần nhất) cho lệnh dựng model.
    Người gọi đã tự truyền --vars, hoặc máy chưa có lần nạp nào, thì để nguyên: dbt lùi về max(order_date) − 1."""
    if not args or args[0] not in NEEDS_VARS or "--vars" in args:
        return args
    done = done if done is not None else loaded_complete_through()
    if done is None:
        print("Chưa có data/last_load.json: dbt đoán ngày trọn = ngày mới nhất có đơn − 1.", flush=True)
        return args
    print(f"Ngày đã trọn theo lúc nạp: {done}", flush=True)
    return args + ["--vars", json.dumps({"complete_through": str(done)})]


def run(args: list[str]) -> int:
    project, key_path, location = settings()  # thiếu .env hay thiếu file khoá thì dừng ở đây, báo rõ
    os.environ.update({"GCP_PROJECT_ID": project, "DATAE_KEYFILE": str(key_path), "BQ_LOCATION": location})
    from dbt.cli.main import dbtRunner

    folder = ["--project-dir", str(TRANSFORM), "--profiles-dir", str(TRANSFORM)]
    # Thêm thư mục vào CUỐI lệnh. Trước đây chèn ngay sau chữ đầu, nên lệnh 2 chữ như "docs generate",
    # "source freshness" thành "docs --project-dir ... generate" và dbt từ chối (No such option), im lặng.
    result = dbtRunner().invoke(with_complete_through(args) + folder)
    if not result.success and result.exception:
        print(f"\ndbt lỗi: {result.exception}", file=sys.stderr)  # đừng để lỗi im lặng
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(run(sys.argv[1:]))
