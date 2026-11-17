# DataE: kho số DEERLY'S cho Claude hỏi

DataE gom Shopify, Meta Ads và Klaviyo của DEERLY'S vào BigQuery, mỗi chỉ số chỉ có 1 định nghĩa. Claude Code đọc kho qua MCP bằng khoá chỉ đọc, nên ai cũng có thể hỏi bằng tiếng Việt và nhận cùng một con số. Dự án làm theo brief "DEERLY Data Lake" 4 tuần của anh Quang, chạy trên BigQuery Sandbox (miễn phí).

## 1. Kho gồm những gì

```
Shopify Admin GraphQL ┐
Meta Insights (ad×ngày)├─ dlt → raw ──dbt──> silver (view) ──dbt──> gold (bảng) ──MCP──> Claude Code
Klaviyo (đếm ngày×msg) ┘                                              │
                                                    forecast.publish ─┘ (dự báo 14 ngày)
```

| Dataset | Có gì | Ai đọc |
|---|---|---|
| `raw` | Dữ liệu thô 3 nguồn, nạp lại cả bảng mỗi lần (load job ghi đè) | Pipeline, dbt |
| `silver` | Đổi kiểu, đổi tên, ngày theo America/Phoenix (`stg_*`, seed tra cứu) | dbt, MCP |
| `gold` | Star schema (`dim_*`, `fct_*`), bảng chỉ số (`daily_performance`, `mart_*`), dự báo | MCP, mọi báo cáo |
| `pii` | Email, tên, địa chỉ khách. Silver/gold chỉ nối qua `customer_key` (sha256 email) | Không ai qua MCP |

- Lịch sử: Shopify từ 11/2024; Meta, Klaviyo từ 1/2026.
- 30 model dbt, 4 seed, 165 test (`transform/`). Mọi bảng và cột silver + gold đều có mô tả, dbt đẩy lên BigQuery lúc build (kiểm: `python -m checks.check_docs`), để AI đọc được schema.
- Định nghĩa chỉ số: [transform/metrics.yml](transform/metrics.yml) (29 chỉ số, mỗi chỉ số có công thức, bảng nguồn và bẫy).

## 2. Hỏi số bằng Claude Code

Mở Claude Code trong thư mục này. `.mcp.json` nạp 2 server (duyệt khi được hỏi; server mới chỉ nạp khi mở phiên mới):

| Server | Làm gì | Khi nào dùng |
|---|---|---|
| `datae` | 15 tool viết sẵn SQL, có cảnh báo bẫy: KPI ngày, tổng khoảng ngày, theo type, sản phẩm, ad, email, khách, cohort, RFM, CLV, ABC/XYZ, bất thường, dự báo | Câu quen thuộc |
| `datae-sql` | MCP Toolbox for Databases v1.16.0: Claude tự viết câu SELECT trên `silver` + `gold` (đọc mô tả cột trước) | Câu ngoài 15 tool |

Ví dụ: "MER và CM ước 7 ngày qua theo ngày Phoenix?", "Hôm qua có gì lạ không?", "2 tuần tới bán khoảng bao nhiêu đơn?", "Top 10 species theo Rev 28 ngày?".

**An toàn:** cả 2 server dùng khoá `datae-mcp` (BigQuery Job User + Data Viewer riêng `silver`, `gold`). Không đọc được `raw`, `pii`, không tạo hay sửa được bảng (`python checks/check_mcp_key.py` 7/7). Toolbox chặn thêm 1 lớp: chỉ SELECT, chỉ 2 dataset, tối đa 200 MB mỗi câu (`python checks/check_toolbox.py` 6/6). Giới hạn: việc này chỉ chặn đường MCP. Claude Code còn có shell, nên trên máy có khoá pipeline (`GOOGLE_APPLICATION_CREDENTIALS`, quyền ghi, đọc được `pii`) thì Claude vẫn có thể đề nghị chạy lệnh dùng khoá đó, và sẽ hỏi trước: hãy từ chối. Máy chỉ để hỏi số thì chỉ để khoá `datae-mcp`.

**5 câu mẫu của brief** đã thử mù ngày 13/11 (phiên mới, chỉ gõ câu hỏi): cả 5 khớp đáp án viết tay ở [checks/sql/check_tuan4_dap_an.sql](checks/sql/check_tuan4_dap_an.sql). Câu 1, 4 dùng tool `datae`; câu 2, 3, 5 Claude tự viết SQL qua `datae-sql`.

**Dashboard** (chạy trên máy, khoá chỉ đọc `datae-mcp`): mở http://127.0.0.1:8600. 5 trang số, menu dọc bên trái: Tổng quan, Quảng cáo & type, Sản phẩm, Khách & email, Cảnh báo & dự báo; thêm 2 trang Hỏi Claude và Báo cáo của tôi. Chọn khoảng ngày (7/14/28 ngày, Tháng này) ở ngay dưới tiêu đề mỗi trang số. Hoàn tiền: ô ở Tổng quan (theo ngày hoàn) và mục Hoàn trả theo dòng sản phẩm ở Sản phẩm (theo ngày đặt, chỉ phần gắn sản phẩm nên nhỏ hơn).

- Backend FastAPI (`webapp/api/`) đọc gold bằng các câu SQL ở `dashboard/queries.py`; giao diện React + Vite 7 + Recharts (`webapp/web/`), backend phục vụ luôn bản đã build.
- **Tự có số mới:** backend xem lần sửa cuối của các bảng gold (metadata, không tốn truy vấn); nạp + dbt build xong thì trong ≤ 60 giây trang tự tải số mới, và backend tính sẵn 5 trang để mở trang không phải chờ.
- **Tự bật khi đăng nhập Windows:** Win+R, gõ `shell:startup`, Enter; trong thư mục vừa mở, chuột phải → New → Shortcut → chọn `D:\Thực tập\DataE\webapp\start.vbs`. Tắt: chạy `webapp\stop.bat`. Log: `logs/webapp.log`.
- Sửa giao diện: `cd webapp/web` rồi `npm run build`. Sửa backend (Python): `webapp\stop.bat` rồi bật lại `webapp\start.vbs`.
- **Hỏi Claude** (mục Claude trên menu): hỏi số ngay trên trang. Backend gọi Claude Code CLI đã đăng nhập trên máy (gói Claude cá nhân, không dùng Claude API, không tốn thêm), chỉ cho 2 server MCP chỉ đọc `datae` + `datae-sql`, tắt mọi tool có sẵn (không đọc file, không chạy lệnh), chạy ở thư mục riêng ngoài dự án. Chỉ dùng cho 1 người trên máy này (`webapp/api/claude_chat.py`).
- **Báo cáo của tôi**, 2 phần: **Bài phân tích** = bấm "Lưu bài phân tích" dưới câu trả lời, lưu bản chụp cố định (chữ Claude viết + tối đa 3 biểu đồ kèm số lúc lưu, ghi ngày trọn cuối của số) vào `webapp/analyses.json`, để sau so lại đã nói và dự báo gì; **Biểu đồ** = Claude đề xuất (SQL + kiểu biểu đồ), xem trước, bấm Lưu thì vào `webapp/reports.json` và tự chạy lại khi có số mới. Cả 2 file không vào git. Backend tự kiểm SQL trước khi chạy: 1 câu SELECT, chỉ bảng gold/silver, ≤ 50 MB (`webapp/api/reports.py`). Báo cáo đã lưu tự chạy lại khi kho có số mới. Sửa 5 trang chính thì vẫn làm trong Claude Code app, không làm từ web.

## 3. Chạy hằng ngày

Một lệnh nạp cả 3 nguồn rồi build kho và cập nhật dự báo (dùng token nguồn và khoá GCP, khoảng 08:00 giờ VN = 18:00 Phoenix):

```bash
python -m pipelines.run
```

Thứ tự: Shopify → Meta → Klaviyo → kiểm raw → `dbt build` → dự báo. Bước nào lỗi thì dừng, mỗi lần chạy ghi 1 dòng vào `logs/runs.jsonl`. Bỏ 1 bước: `--skip meta`; một khoảng ngày cho Meta, Klaviyo: `--since 2026-11-01 --until 2026-11-07`.

Sau đó đối chiếu với chính hệ thống nguồn (đơn Shopify `ordersCount`, spend Meta cấp tài khoản, Placed Order Klaviyo):

```bash
python checks/reconcile.py
```

Lưu ý khi chạy:
- Ngày mới nhất trong kho luôn đang dở (Phoenix mới 18:00). Mọi tool và mô tả đều coi ngày trọn cuối = ngày mới nhất − 1.
- App Meta dùng chung với đội ads (giới hạn request chung). Pipeline tự giãn và tự dừng khi chạm giới hạn; gom lịch sử lớn thì chạy ngoài giờ và báo trước.
- Chưa bật lịch chạy tự động: brief yêu cầu chờ anh Quang review.

## 4. Cài trên máy mới

1. Python 3.13, rồi `python -m pip install -r requirements.txt` (`pip.exe` có thể bị Application Control chặn).
2. BigQuery, khoá, `.env`: làm theo [docs/cai-dat-bigquery.md](docs/cai-dat-bigquery.md) mục 1–10 (project, 2 service account `datae-pipeline` và `datae-mcp`, authorized dataset cho silver, tải `bin/toolbox.exe` kèm kiểm SHA256).
3. `.env` cần: `GCP_PROJECT_ID`, `GOOGLE_APPLICATION_CREDENTIALS`, `MCP_CREDENTIALS`, `BQ_LOCATION` và token Shopify, Meta, Klaviyo. Kiểm tên biến (không in giá trị bí mật): `python checks/check_env_names.py`.
4. `python -m pipelines.setup_datasets`, rồi `python -m pipelines.run`.

dbt luôn chạy qua `python -m pipelines.dbt <lệnh>` (`dbt.exe` bị Application Control chặn; file này cũng trỏ đúng `transform/` và khoá).

## 5. Kiểm tra

| Lệnh | Kiểm gì |
|---|---|
| `python -m pipelines.dbt build` | Build + 165 test dbt (bình thường WARN 1 = 51 ad Meta đã xoá) |
| `python checks/check_raw.py` | Raw đủ bảng, đủ ngày, không trùng |
| `python checks/reconcile.py` | Kho khớp hệ thống nguồn |
| `python checks/check_mcp_sql.py` | Dry run 22 câu SQL của server `datae` |
| `python checks/check_mcp_key.py`, `python checks/check_toolbox.py` | Khoá và Toolbox chỉ đọc |
| `python -m checks.check_docs` | Độ phủ mô tả bảng/cột (cả trên BigQuery sau `docs generate`) |
| `python tests/test_<tên>.py` | 16 bộ test Python, không gọi API, không dùng khoá |

## 6. Chỗ khác brief

| Brief | DataE | Vì sao |
|---|---|---|
| Partition theo ngày, budget alert 10 USD | Không partition, không budget alert | Sandbox xoá partition cũ hơn 60 ngày và không có billing để đặt alert. Chi phí hiện 0 USD (miễn phí 1 TB truy vấn/tháng) |
| dlt incremental theo `updated_at` | Nạp lại cả bảng bằng load job ghi đè | Sandbox không có DML (MERGE, INSERT) |
| Meta 13 tháng, Klaviyo 12 tháng | Meta, Klaviyo từ 1/2026 | Đã chốt mốc lịch sử; app Meta dùng chung giới hạn với đội ads |
| `stg_klaviyo_events` (event thô) | `stg_klaviyo_message_daily` (đếm ngày × message) | Event thô có email người nhận (PII) |
| Cổng khớp số với `morning.html` | Đối chiếu thẳng hệ thống nguồn (`reconcile.py`) | Anh Quang chốt 12/11 (mục 7) |
| MCP Toolbox (genai-toolbox) | Toolbox `datae-sql` + server riêng `datae` 15 tool | Câu quen dùng tool đã kiểm có bẫy; câu lạ Claude tự viết SQL |
| Khoá đọc silver + gold | Đúng như brief, silver đọc qua authorized dataset của `raw` | View silver đọc `raw`, nhưng khoá MCP không được đọc `raw` |
| `context/metrics.md`, `cogs.csv` | `metrics.yml` trạng thái "tạm", CM ước dùng giá vốn tạm 28% + phí 3,8% | Chưa nhận 2 file này |
| Một số câu mẫu tính thẳng từ fact | Câu 3 (mua lần 2 / 60 ngày) có bảng `gold.mart_repeat_60d` | Dễ sai: phải bỏ khách chưa đủ 60 ngày, đơn huỷ, đơn cùng ngày |

## 7. Còn chờ anh Quang

- `context/cogs.csv` (giá vốn thật cho CM ước) và `context/metrics.md` (chốt định nghĩa chỉ số).
- Chỗ lưu bản dự báo cũ và ảnh chụp RFM (Sandbox xoá bảng sau 60 ngày, không MERGE), billing, repo, người review, lịch chạy tự động.
- Lịch sale riêng của shop, lịch gửi campaign email, hạn giao trước Giáng sinh (thêm vào `transform/seeds/events.csv`).
- Nghĩa các tiền tố SKU suy từ tên (`transform/seeds/product_lines.csv`, nhất là DL0, DL1).

## 8. Thư mục

| Thư mục | Có gì |
|---|---|
| `pipelines/` | Nạp 3 nguồn, `run.py` chạy cả hệ, `dbt.py` gọi dbt |
| `transform/` | dbt: `models/staging` (silver), `models/marts` (gold), `seeds/`, `tests/`, `metrics.yml` |
| `forecast/` | Backtest và ghi dự báo 14 ngày (ETS + mô hình theo spend) |
| `mcp_server/` | Server MCP `datae` (15 tool) |
| `mcp_toolbox/` | Cấu hình và lệnh chạy MCP Toolbox `datae-sql` |
| `dashboard/` | `queries.py` câu SQL + `kpi.py` phép tính, backend React dùng |
| `webapp/` | Dashboard React: `api/` (FastAPI), `web/` (React), `start.vbs` / `stop.bat` |
| `checks/` | Script kiểm (reconcile, khoá, docs...), `explore_*` khám phá nguồn mới; `sql/check_tuan4_dap_an.sql` đáp án 5 câu mẫu, `sql/da-kiem/` câu kiểm từng mô hình đã chạy |
| `tests/` | Test Python |
| `docs/` | Cài BigQuery, khám phá nguồn, schema Meta, bảng raw, [kịch bản demo bàn giao](docs/demo-ban-giao.md) |
| `tasks/` | `todo.md` (kế hoạch, kết quả từng bước), `lessons.md` (bài học) |
| `data/`, `logs/` | Bộ nhớ đệm nguồn và log chạy trên máy (không đưa lên repo) |

## Phụ lục: cổng khớp số (tuần 3)

**Quyết định 2026-11-12 (anh Quang):** bỏ qua so với `dashboard/morning.html`. Kho lấy số thẳng từ hệ thống nguồn
(Shopify Admin API, Meta Insights, Klaviyo), nên đối chiếu với chính nguồn là đủ. Đối chiếu nguồn chạy bằng
`python checks/reconcile.py` (kết quả ở `logs/reconcile.json`).

Đối chiếu nguồn 7 ngày đã đóng 4–10/11 (giờ Phoenix), chạy 2026-11-12 08:13 giờ VN:

| Chỉ số | Nguồn (hệ thống) | Kho DataE | Lệch |
|---|---|---|---|
| Đơn Shopify | 778 (`ordersCount`) | 778 | 0% |
| Spend Meta | 23.697,15 (cấp tài khoản) | 23.696,91 (cộng cấp ad) | −0,001%, mọi ngày < 1 USD |
| Placed Order Klaviyo | 779 | 779 | 0% |

Chỉ số tính từ số trên (`gold.mart_daily_kpi`, định nghĩa ở `transform/metrics.yml`), 4–10/11:

| Ngày | Rev | Đơn | Spend | MER | CM ước |
|---|---|---|---|---|---|
| 2026-11-04 | 5.520,21 | 100 | 3.174,13 | 1,74 | 590,65 |
| 2026-11-05 | 4.567,60 | 93 | 3.409,66 | 1,34 | −294,56 |
| 2026-11-06 | 6.046,35 | 98 | 3.336,44 | 1,81 | 787,17 |
| 2026-11-07 | 6.366,77 | 128 | 3.435,71 | 1,85 | 906,43 |
| 2026-11-08 | 6.650,68 | 112 | 3.453,74 | 1,93 | 1.082,02 |
| 2026-11-09 | 6.526,77 | 121 | 3.143,38 | 2,08 | 1.307,88 |
| 2026-11-10 | 6.281,82 | 126 | 3.743,85 | 1,68 | 540,35 |
| **7 ngày** | **41.960,20** | **778** | **23.696,91** | **1,77** | **4.919,94** |

Ghi chú:
- Rev = Shopify `current_total` theo ngày đặt (đã trừ hoàn, sửa đơn); đơn tính cả đơn huỷ. Rev chưa đối chiếu riêng
  với một báo cáo doanh thu của Shopify; đơn khớp `ordersCount` và Rev là tổng cột của chính các đơn đó.
- CM ước dùng giá vốn tạm 28% và phí 3,8% (brief), chờ `cogs.csv`. MER hoà vốn ≈ 1,47.

## Analytics app nâng cấp (17/11/2026)

Giao diện DEERLY’S với demo không credential, trình khám phá campaign/sản phẩm, CLV lịch sử, từ điển metric và bằng chứng coverage; biểu đồ live có preview/sửa, bản chụp cố định được giữ riêng. Xem [cách chạy chính xác và hợp đồng dữ liệu](docs/analytics-app.md), [bằng chứng QA và giới hạn xác minh](docs/analytics-qa.md).

Chạy demo sau khi cài dependency và build frontend: `bash scripts/demo.sh`, mở http://127.0.0.1:8600. Không chạy pipeline hoặc đọc `.env` để thử demo.

Lượt nâng cấp tiếp theo bổ sung URL giữ bộ lọc, preview chống phản hồi cũ, hủy sửa đổi có xác nhận, dừng/gửi lại chat và phục hồi trạng thái lưu gián đoạn. `npm --prefix webapp/web test` hiện tự dựng demo kiểm thử riêng ở 8601; không cần trỏ test vào preview 8600.


## Repository dataleka

Đích phát hành: `dataleka` PRIVATE trong tài khoản GitHub đã đăng nhập. `scripts/prepare_release.py` đóng gói snapshot nguồn xác định, kiểm mẫu credential và giữ riêng runtime/nội dung đã lưu. Sau `gh auth login`, `bash scripts/publish_github.sh` tạo repo mới và kiểm commit remote khớp local; không sửa origin hoặc index của workspace gốc. Workflow `Verify dataleka locally-equivalent demo` chỉ chạy bằng `workflow_dispatch`, không tự nạp dữ liệu hay deploy.
