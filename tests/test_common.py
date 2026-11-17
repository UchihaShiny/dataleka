"""Kiểm đường ống dlt → JSONL → load job bằng BigQuery giả. Không dùng khoá, không gọi mạng.

Chạy từ thư mục gốc:  python tests/test_common.py
"""

import sys
import tempfile
from pathlib import Path

import dlt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from pipelines import common  # noqa: E402


def demo_source(rows: int):
    @dlt.resource(name="orders", primary_key="id")
    def orders():
        for i in range(rows):
            yield {"id": i, "total": i * 1.5, "items": [{"sku": f"S{i}", "qty": 1}, {"sku": f"T{i}", "qty": 2}]}

    return orders


class FakeTable:
    def __init__(self, rows):
        self.num_rows = rows


class FakeJob:
    def result(self):
        return self


class FakeBigQuery:
    """Ghi lại các load job; WRITE_TRUNCATE thay toàn bộ bảng như BigQuery thật."""

    project = "gia-lap"

    def __init__(self):
        self.tables, self.configs, self.schemas = {}, [], {}

    def load_table_from_file(self, handle, table_id, job_config):
        self.configs.append(job_config)
        rows = sum(1 for line in handle if line.strip())
        assert job_config.source_format == "NEWLINE_DELIMITED_JSON"
        self.schemas[table_id] = {f.name: f.field_type for f in job_config.schema}
        assert job_config.write_disposition == "WRITE_TRUNCATE"
        self.tables[table_id] = rows
        return FakeJob()

    def get_table(self, table_id):
        return FakeTable(self.tables[table_id])


with tempfile.TemporaryDirectory() as folder:
    data_dir = Path(folder)
    bq = FakeBigQuery()

    loaded = common.run(demo_source(100), "demo", "demo", bq=bq, data_dir=data_dir)
    # dlt tách list lồng nhau thành bảng con, giống line items của đơn hàng
    assert loaded == {"orders": 100, "orders__items": 200}, loaded
    assert set(bq.tables) == {"gia-lap.raw.demo_orders", "gia-lap.raw.demo_orders__items"}

    # Chạy lần 2: ghi đè, không cộng dồn
    loaded = common.run(demo_source(100), "demo", "demo", bq=bq, data_dir=data_dir)
    assert bq.tables["gia-lap.raw.demo_orders"] == 100 and bq.tables["gia-lap.raw.demo_orders__items"] == 200
    # Schema lấy từ dlt, không để BigQuery đoán
    schema = bq.schemas["gia-lap.raw.demo_orders"]
    assert schema["id"] == "INT64" and schema["total"] == "FLOAT64" and "_dlt_id" in schema, schema

    # Nguồn trả ít dòng hơn: bảng cũng ít đi, không giữ dòng cũ
    common.run(demo_source(30), "demo", "demo", bq=bq, data_dir=data_dir)
    assert bq.tables["gia-lap.raw.demo_orders"] == 30, bq.tables

    common.reset("demo", data_dir)
    assert not (data_dir / "demo").exists()

print("PASS: dlt ra JSONL, tách bảng con, ghi đè không trùng, số dòng khớp")
