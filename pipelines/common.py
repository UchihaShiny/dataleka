"""Đường ống dùng chung cho mọi nguồn: dlt → JSONL trên máy → BigQuery bằng load job ghi đè.

- Không cho dlt ghi thẳng vào BigQuery: project chạy Sandbox, không có DML (INSERT, MERGE) mà dlt
  cần. Load job thì Sandbox cho phép.
- Không dùng Parquet: Application Control trên máy chặn DLL Parquet của pyarrow.
- Mỗi bảng gộp thành 1 file, nạp bằng 1 load job WRITE_TRUNCATE với schema lấy từ dlt, nên chạy lại
  không trùng, kiểu cột không bị BigQuery tự đoán, và bảng không bao giờ ở trạng thái nạp dở.
"""

import gzip
import shutil
import sys
import tempfile
from pathlib import Path

import dlt

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATASET = "raw"
PII_PREFIX = "pii_"  # bảng có tên bắt đầu bằng pii_ vào dataset pii, không vào raw

# Kiểu dữ liệu của dlt → BigQuery
BQ_TYPES = {
    "text": "STRING", "bigint": "INT64", "double": "FLOAT64", "bool": "BOOL",
    "timestamp": "TIMESTAMP", "date": "DATE", "time": "TIME", "decimal": "NUMERIC",
    "json": "JSON", "binary": "BYTES", "wei": "BIGNUMERIC",
}


def extract(source, pipeline_name: str, data_dir: Path = DATA) -> tuple[dict[str, list[Path]], dict]:
    """Chạy dlt ra JSONL. Trả về ({bảng: [file]}, {bảng: cột dlt}), bỏ bảng nội bộ _dlt_*."""
    bucket = data_dir / pipeline_name
    pipeline = dlt.pipeline(
        pipeline_name=pipeline_name,
        destination=dlt.destinations.filesystem(bucket_url=bucket.as_uri()),
        dataset_name=DATASET,
        pipelines_dir=str(data_dir / ".dlt"),
    )
    info = pipeline.run(source, loader_file_format="jsonl", write_disposition="replace")
    info.raise_on_failed_jobs()
    tables = pipeline.default_schema.data_tables()
    files, columns = {}, {}
    for table in tables:
        name = table["name"]
        parts = sorted((bucket / DATASET / name).glob("*.jsonl*"))
        if parts:
            files[name] = parts
            columns[name] = table["columns"]
    return files, columns


def bigquery_schema(columns: dict) -> list:
    from google.cloud import bigquery

    return [
        bigquery.SchemaField(name, BQ_TYPES[column["data_type"]],
                             mode="NULLABLE" if column.get("nullable", True) else "REQUIRED")
        for name, column in columns.items()
        if column.get("data_type")
    ]


def combine(parts: list[Path], target: Path) -> int:
    """Gộp các file JSONL (có thể nén gzip) của một bảng thành 1 file, trả số dòng."""
    rows = 0
    with target.open("wb") as out:
        for part in parts:
            opener = gzip.open if part.read_bytes()[:2] == b"\x1f\x8b" else open
            with opener(part, "rb") as handle:
                for line in handle:
                    if line.strip():
                        out.write(line if line.endswith(b"\n") else line + b"\n")
                        rows += 1
    return rows


def target(project: str, prefix: str, name: str) -> str:
    """raw.<nguồn>_<bảng>, riêng bảng pii_* vào pii.<nguồn>_<bảng bỏ pii_>."""
    if name.startswith(PII_PREFIX):
        return f"{project}.pii.{prefix}_{name[len(PII_PREFIX):]}"
    return f"{project}.{DATASET}.{prefix}_{name}"


def load(files: dict[str, list[Path]], columns: dict, prefix: str, bq=None) -> dict[str, int]:
    """Nạp từng bảng vào BigQuery, ghi đè cả bảng và schema. Lệch số dòng thì dừng."""
    from google.cloud import bigquery

    if bq is None:
        from pipelines.bq import client

        bq = client()
    loaded = {}
    with tempfile.TemporaryDirectory() as folder:
        for name, parts in files.items():
            table_id = target(bq.project, prefix, name)
            combined = Path(folder) / f"{name}.jsonl"
            rows = combine(parts, combined)
            config = bigquery.LoadJobConfig(
                source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
                write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
                schema=bigquery_schema(columns[name]),
            )
            with combined.open("rb") as handle:
                bq.load_table_from_file(handle, table_id, job_config=config).result()
            in_bigquery = bq.get_table(table_id).num_rows
            print(f"  {table_id}: {rows:,} dòng trong file, {in_bigquery:,} dòng trong BigQuery")
            if in_bigquery != rows:
                sys.exit(f"LỖI: {table_id} lệch số dòng ({rows} so với {in_bigquery})")
            loaded[name] = rows
    return loaded


def run(source, pipeline_name: str, prefix: str, bq=None, data_dir: Path = DATA) -> dict[str, int]:
    """Lấy dữ liệu bằng dlt rồi nạp vào raw. prefix là tên nguồn, ví dụ shopify, meta, klaviyo."""
    print(f"== {pipeline_name}: lấy dữ liệu ==")
    files, columns = extract(source, pipeline_name, data_dir)
    print(f"== {pipeline_name}: nạp {len(files)} bảng vào BigQuery ==")
    return load(files, columns, prefix, bq)


def reset(pipeline_name: str, data_dir: Path = DATA) -> None:
    """Xoá file và trạng thái dlt của một nguồn trên máy. Không đụng BigQuery."""
    shutil.rmtree(data_dir / pipeline_name, ignore_errors=True)
    shutil.rmtree(data_dir / ".dlt" / pipeline_name, ignore_errors=True)
