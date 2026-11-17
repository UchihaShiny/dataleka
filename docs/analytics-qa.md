# QA — DEERLY’S Analytics, 17/11/2026

## Phạm vi và baseline

Repository gốc: `/home/shiny/PycharmProjects/DataLake`. Không tìm thấy AGENTS.md trong chuỗi thư mục cha hoặc trong project. Đã đọc README, PROGRESS, tasks/lessons, todo, manifests, metrics.yml, query/backend/frontend và các model/test liên quan. Giữ thay đổi .idea có sẵn; không reset hay xóa nội dung đã lưu.

Baseline chạy từ bản `git archive HEAD` tại `/tmp/datae-baseline`, tách với workspace và tắt dotenv:

- **15/16 suite Python đạt.** `test_claude_chat` lỗi vì `command()` tìm Claude executable trước khi kiểm session_id sai. Đã đổi thứ tự validation, không cần cài/đăng nhập Claude để test malformed session.
- Frontend ban đầu build được. `npm ci`/audit ghi nhận **1 dependency high** ở Vite 7.1.12. Cập nhật trong Vite 7 lên **7.3.8**, audit cuối **0 vulnerability**. Giữ React/Recharts hiện hữu.
- Máy thiếu Node/npm trong PATH và Python ensurepip. Dựng `.venv` bằng uv; dependency từ requirements.txt cài thành công; Node 22.16.0 dùng thư mục /tmp riêng.

## Luồng dữ liệu đã truy vết

`pipelines.run` điều phối Shopify → Meta → Klaviyo → check_raw → dbt build → forecast.publish, dừng khi lỗi. Nguồn vào dlt/raw; silver staging chuyển America/Phoenix; gold fct_orders loại test, current_total đã trừ hoàn. fct_lines giữ doanh thu dòng sau hoàn không gồm ship/thuế. Các mart có quy tắc riêng: ABC/repeat loại đơn huỷ, RFM snapshot theo ngày mới nhất, cohort/CLV tháng lịch vẫn gồm đơn hủy theo model.

Dashboard đọc query gold có DATE parameters qua khóa chỉ đọc, tối đa 50 MiB/query; `pages.py` tổng hợp và clean JSON; FastAPI cache theo phiên bản bảng; React lấy meta rồi page contract. Forecast publish (chỉ đọc mã nguồn và chạy test giả) tạo 14 dòng ETS và spend model với backtest; app chỉ đọc kết quả đã công bố, kiểm cận/mốc. MCP cố định tối đa 200 MiB/query, SQL toolbox chỉ SELECT gold/silver; Claude CLI tắt built-in tools và chỉ cho hai MCP. Đã bỏ fallback khóa pipeline ở MCP chính.

## Kết quả kiểm tra

- **17/17 suite Python PASS**, mỗi suite process riêng, `PYTHON_DOTENV_DISABLED=1`. Bao gồm test nguồn/pipeline bằng mock, forecast/backtest bằng synthetic data, SQL/report guardrails và các test dashboard cũ.
- **12 test product mới PASS**: cùng page/API contracts không cloud/network, arithmetic độc lập với Decimal, tổng campaign/type/product, hoàn tiền cộng dồn giữa kỳ, thiếu ngày dù hai kỳ có cùng số dòng, null/zero/NaN, biên nửa đêm Phoenix, forecast thiếu ngày/sai cận/cũ, preview/save/edit/reopen/delete, snapshot bất biến, storage JSON hỏng giữ nguyên, malformed requests, outage/recovery, không fallback khóa pipeline, schema query mới khớp mô tả model và parse BigQuery SQL bằng sqlglot.
- **7/7 test Playwright PASS** trên Chromium headless, frontend production do FastAPI tại 127.0.0.1:8600 phục vụ. Một test quét 8 trang × 4 viewport (1440×1000, 768×1024, 390×844, 360×800) × 2 theme. Không page overflow hoặc lỗi JavaScript phát hiện được. Các hành trình khác kiểm bộ lọc/detail/CSV, phản hồi đến trễ, outage/retry, create/preview/save/edit/reopen/delete có xác nhận, Ask demo/snapshot và mobile keyboard/reduced motion.
- **axe WCAG 2 A/AA + 2.1 A/AA: 0 violation được phát hiện** trên 8 trang, cả hai theme. Đã sửa accessible name theme/sort và màu chữ ô cohort. Đây là audit tự động trong các trạng thái đã thử, không thay thế kiểm toán accessibility thủ công toàn bộ.
- Production build thành công: 458 modules; JS ~635 kB (~182 kB gzip), CSS ~19,5 kB. Không thêm asset/font từ dịch vụ ngoài.
- Python compile, SQL schema/static checks, `git -c core.whitespace=cr-at-eol diff --check` đạt. Dùng cr-at-eol vì repo có các file CRLF gốc.

Log gọn: [Python suites](qa/python-suites.txt), [product regression](qa/product-tests.txt), [browser summary](qa/browser-summary.json). Các lệnh chạy lại trong [analytics-app.md](analytics-app.md).

## Kiểm tra hình ảnh

Playwright tạo 32 ảnh full-page (8 trang × desktop/mobile × hai theme). Đã mở xem ảnh tổng quan desktop/mobile cả sáng/tối, sản phẩm desktop và khách hàng mobile; kiểm tra các biểu đồ, vùng bảng cuộn ngang và typography. Mỗi theme được xác nhận từ html[data-theme] trước chụp, không suy ra từ tên file.

Bản ảnh chọn để bàn giao (toàn bộ số là giả lập):

- [Tổng quan desktop sáng](qa/overview-desktop-light.png), [desktop tối](qa/overview-desktop-dark.png).
- [Tổng quan mobile sáng](qa/overview-mobile-light.png), [mobile tối](qa/overview-mobile-dark.png).
- [Sản phẩm desktop](qa/products-desktop-light.png), [khách mobile](qa/customers-mobile-dark.png).

## Giới hạn bằng chứng và việc còn cần ở live

Không đọc file .env thật, credential hay PII; không chạy ingestion, reconcile, dbt/cloud dry run có credential, forecast publish thật, Claude thật, deployment hay schedule. Các test nguồn là test mock/synthetic; các pass này **không chứng minh** số liệu production hay quyền IAM thực tế đúng. Query mới được kiểm schema cục bộ và parser, vẫn cần người vận hành xác minh bằng khóa chỉ đọc trên kho thật. Chưa thử Safari/Firefox, screen reader thật hoặc tình huống đa người dùng.

CM vẫn dùng giá vốn tạm 28% và phí 3,8% từ dbt vars; chưa phải lãi ròng. CLV là doanh thu lịch sử, không phải giá trị tương lai/lợi nhuận. Forecast chưa mô hình hóa BFCM/sự kiện và không giữ lịch sử forecast ở kho hiện tại. Health chỉ biết coverage theo dòng gold, mốc load_status và độ trễ ngày quan sát; không biết SLA nạp/đối soát nguồn nếu không có bằng chứng. Khám phá/CSV có giới hạn 1.000 dòng aggregate và báo khi bị cắt. Ứng dụng tiếp tục dành cho localhost một người dùng, chưa sẵn sàng làm dịch vụ public.


## Lượt nâng cấp 2 — thao tác, URL và vòng đời chat

Tiếp tục trên toàn bộ thay đổi chưa commit của lượt trước, giữ các file .idea và kho lưu người dùng. Bổ sung:

- URL bộ lọc/sắp xếp/phân trang; kiểm reload, Back và kỳ ngày không làm mất trạng thái.
- CSV số âm không bị đổi thành text, bảo vệ công thức ở ô chuỗi; unit kiểm cả dấu phẩy, xuống dòng, quote, 0 và null.
- Preview bị hủy khi sửa spec, revision guard chặn kết quả đến trễ; xác nhận bỏ sửa đổi; backend chỉ cho cột Y số/null và cảnh báo 500 dòng.
- Hỏi Claude: Dừng trả lời, Gửi lại, thời gian chờ và retry preview. Reload sau lưu gián đoạn ghi rõ kết quả lưu chưa biết và yêu cầu kiểm danh sách trước khi lưu lại. Không cho snapshot âm thầm bỏ các chart preview lỗi.
- SSE parser kiểm chunk UTF-8, CRLF, multiline data, nhiều frame, frame hỏng/đứt và giới hạn buffer. ASGI stream có queue tối đa 32 events, cancel event theo disconnect, dừng CLI và nhả khóa. Stderr không đọc chặn hoặc trả nguyên văn ra UI.
- Browser test tự chạy FastAPI demo ở **8601** trong thư mục tạm mới, `reuseExistingServer=false`; không dùng preview/live 8600.

Kết quả lượt này: **18/18 suite Python**, gồm **5 kiểm tra lifecycle/kiểu dữ liệu chart**; **4/4 unit JavaScript**; **14/14 browser tests**. Audit accessibility 8 trang × 2 theme và kiểm responsive 8 trang × 4 viewport × 2 theme vẫn nằm trong bộ browser. Build production khoảng 640 kB JS (183 kB gzip), 460 modules. Dependency audit 0 vulnerability; compile và whitespace check đạt.

Bằng chứng: [Python suites lượt 2](qa/python-suites-upgrade2.txt), [lifecycle regression](qa/chat-lifecycle-tests.txt), [browser lượt 2](qa/browser-upgrade2-summary.json). Các screenshot lựa chọn đã cập nhật từ bản build lượt này; các screenshot chỉ chứa fixture tổng hợp.

Giới hạn không đổi: chưa chạy Claude/BigQuery thật, chưa chứng minh việc dừng toàn bộ tiến trình con MCP trên mọi hệ điều hành. Cancel/lock/ASGI disconnect được kiểm bằng process giả và local streams, browser bằng demo/mô phỏng outage. Không mở rộng tool privileges, không sửa metrics.yml hay eligibility/cancellation rules trong dbt.


Trong vòng cuối, test fixture sessionStorage từng bị race với lần mount đầu (12 pass/1 fail); đã đưa seed vào addInitScript trước ứng dụng và lặp riêng test này 3 lần đều đạt. Kiểm ảnh mobile còn tìm ra sticky composer che lỗi/retry; đã chuyển composer về luồng trang, cuộn tới sau form và thêm regression kiểm hình học + bấm retry thật trên viewport 390 px. [Ảnh phục hồi chat mobile](qa/ask-recovery-mobile-dark.png), [bộ lọc từ URL trên desktop](qa/explorer-link-desktop-light.png).


## Phát hành dataleka

19/19 suite Python PASS, trong đó `test_release.py` có 4 test: loại trừ runtime/saved content, ZIP xác định và credential guard (kể cả shell), symlink, private publish giả lập bằng Git bare kiểm SHA và giữ repo gốc. Log `qa/python-suites-dataleka.txt`, `qa/release-tests.txt`. GitHub CLI thực tế tạo repo UchihaShiny/dataleka PRIVATE và push main; SHA đối chiếu bằng Git remote và GitHub API. CI chỉ manual trigger và chưa chạy trên GitHub; Docker/Cloudflare chưa được kiểm thử hay deploy.
