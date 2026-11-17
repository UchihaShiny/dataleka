# DEERLY’S Analytics — chạy và kiểm tra cục bộ

Ứng dụng giữ FastAPI, React 18, Vite 7, Recharts 2 và các kết nối hiện có. Không triển khai hay kích hoạt lịch chạy. Chỉ phục vụ localhost; kiến trúc hiện tại dành cho một người dùng trên máy, chưa có xác thực đa người dùng.

## Chạy demo không credential

Yêu cầu Python 3.13, Node 22.16+ (hoặc Node 24) và npm. Từ thư mục repository:

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
npm --prefix webapp/web ci
npm --prefix webapp/web run build
bash scripts/demo.sh
```

Nếu máy có Python venv/pip đầy đủ, hai lệnh đầu có thể thay bằng `python3 -m venv .venv` rồi `.venv/bin/python -m pip install -r requirements.txt`.

Preview: **http://127.0.0.1:8600**. Bản production `dist` được chính FastAPI phục vụ, không cần Vite dev server.

Lệnh backend tương đương, đã kiểm tra trên workspace này:

```bash
DATAE_MODE=demo PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m uvicorn webapp.api.main:app --host 127.0.0.1 --port 8600
```

Môi trường ban đầu không có Node/npm trong PATH và thiếu ensurepip. Lượt đầu dùng công cụ tại /tmp; các file tạm có thể mất khi phiên đổi. Node 22.16.0 hiện được đặt trong `bin/node-v22.16.0-linux-x64` (gitignored); `.venv` vẫn dùng riêng. Nếu dùng đúng workspace hiện tại:

```bash
export PATH="$PWD/bin/node-v22.16.0-linux-x64/bin:$PATH"
```

Demo là adapter DataFrame tổng hợp cố định, mốc 15/11/2026 Phoenix, qua cùng query identifiers → `pages.py` → API → React như live. Không mô phỏng ingestion/dbt hay chạy mô hình thống kê thật. CM fixture dùng Decimal, làm tròn HALF_UP như BigQuery NUMERIC. Các tổng spend campaign/type và doanh thu sản phẩm/type được đối chiếu với fixture KPI.

- Phải bật bằng `DATAE_MODE=demo`. Live lỗi không tự đổi sang demo.
- Nhãn DEMO luôn hiển thị. Không tạo BigQuery client, gọi nguồn kinh doanh hay gọi Claude.
- SQL tùy ý không được giả vờ thực thi. Demo chỉ nhận đúng SQL mẫu được công bố bởi `/api/demo/spec` (đổi tên/loại/trục hợp lệ được phép).
- Ask demo trả bài mẫu có nhãn rõ, không phải phản hồi AI cho câu hỏi tùy ý.
- Lưu mặc định ở `data/demo/{reports,analyses}.json`; chat dùng `sessionStorage['datae-chat-demo']`. Live vẫn giữ nguyên `webapp/{reports,analyses}.json` và `datae-chat`.
- Có thể đổi riêng thư mục demo bằng `DATAE_DEMO_STORE=/tmp/deerlys-demo`. Không trỏ biến này vào nơi chứa nội dung thật.

## Chế độ live và quyền truy cập

Người vận hành tự cấu hình khóa **datae-mcp chỉ đọc** theo tài liệu BigQuery hiện có. Lệnh `DATAE_MODE=live .venv/bin/python -m uvicorn webapp.api.main:app --host 127.0.0.1 --port 8600` giữ cơ chế cấu hình hiện tại. Không dùng khóa pipeline cho analytics. Cả MCP chính lẫn dashboard đều kiểm identity khóa datae-mcp, từ chối nếu thiếu hoặc sai.

Phiên nâng cấp này không đọc `.env`, không thử credential thật, không chạy ingestion/reconcile/dbt/cloud dry run/Claude thật. Không thể dùng kiểm tra demo làm bằng chứng đối soát số thật. Bản live vẫn cần người vận hành chạy dry run bằng khóa chỉ đọc và xác minh số trên kho của họ trước khi sử dụng quyết định kinh doanh.

## Các hành trình

- Tổng quan: 7/14/28 ngày hoặc tháng tới ngày trọn, kỳ trước cùng độ dài. MER/AOV/CPO từ tổng thành phần. Thiếu ngày thì không công bố tổng cả kỳ hay so sánh; biểu đồ để trống ngày thiếu. Hoàn tiền theo ngày hoàn hiển thị riêng; Rev đã trừ hoàn.
- Quảng cáo: chỉ số type, cảnh báo theo ngưỡng chưa làm tròn; không coi `(không theo type)` là type lỗ. Campaign tìm kiếm, lọc dòng, sắp xếp, phân trang 10 dòng, chi tiết, CSV tổng hợp sau lọc. Meta attribution không phải incremental sales.
- Sản phẩm: khám phá theo kỳ dùng fct_lines (kể cả đơn hủy theo thiết kế fact), doanh thu dòng không gồm ship/thuế; returns theo ngày đặt. ABC cố định 90 ngày giữ quy tắc loại đơn huỷ/non-product của model hiện hữu.
- Khách: tuần trọn, repeat 60 ngày đủ điều kiện, RFM loại đơn hủy và ghi as_of riêng (có thể là ngày dở theo model), cohort tháng lịch với dấu `*`, CLV doanh thu lịch sử có mean/median/CI95. Không sửa các quy tắc model khác nhau thành một quy tắc chung.
- Cảnh báo: observed/expected; forecast 14 ngày liên tiếp có kiểm cận, mốc và nhãn forecast cũ. Dải ngày khác khoảng cho tổng từ sai số backtest; chưa biết lễ/BFCM. Không thêm kịch bản spend vượt giới hạn của MCP.
- Chỉ số & dữ liệu: đọc trực tiếp 29 định nghĩa từ metrics.yml; ngày đầu/cuối và số ngày có dòng từ gold. Đối soát/giờ nạp nguồn vẫn unknown. `built_at` là lúc dbt dựng load_status, không phải lúc dữ liệu nguồn cập nhật.
- Báo cáo: biểu đồ live được xem trước, lưu, mở, sửa và xác nhận xóa. Bản chụp giữ chữ và số tại lúc lưu; không tự cập nhật hay chỉnh lại lịch sử. File hỏng được giữ nguyên và báo lỗi, không ghi đè bằng danh sách trống.
- Ask: gợi ý, trạng thái công cụ/SSE, lỗi kết thúc sớm, preview, lưu live chart hoặc fixed snapshot. Giữ nguyên CLI không built-in tools, hai MCP chỉ đọc, SQL SELECT gold/silver, dry run và byte/row limits. Đổi theme không remount và làm mất hội thoại.

Khám phá bị giới hạn **1.000 dòng tổng hợp đầu** theo spend/revenue; API lấy thêm một dòng để phát hiện truncation và giao diện báo rõ. CSV chỉ bao gồm các dòng trong tập đó khớp bộ lọc, không phải full warehouse export. CSV escape công thức và ký tự đặc biệt. Không xuất customer/order identifiers.

## Kiểm tra lặp lại

```bash
.venv/bin/python scripts/test_local.py
npm --prefix webapp/web run build
npm --prefix webapp/web exec -- playwright install chromium
npm --prefix webapp/web test -- --timeout=120000
npm --prefix webapp/web audit --audit-level=low
```

Browser test tự khởi động FastAPI demo riêng ở **8601**, dùng thư mục lưu tạm mới cho mỗi lần chạy và dọn sau khi kết thúc. Không cần mở backend bằng tay. Playwright từ chối tái sử dụng server đang chiếm cổng đó; preview 8600 được giữ riêng. Test tạo các mục có tên QA và xóa đúng các mục mình vừa tạo. Toàn bộ test Python chạy mỗi file trong process riêng và tắt dotenv. Dữ liệu lưu của người dùng không được reset. Kết quả và giới hạn kiểm tra: [analytics-qa.md](analytics-qa.md).


## Đợt nâng cấp tiếp theo: khôi phục và thao tác an toàn

- Bộ lọc khám phá nằm trong URL: `q`, `line`, `sort`, `dir`, `p`, cùng `preset`. Reload/mở lại link giữ trạng thái; typing thay URL hiện tại để không làm rối lịch sử Back. Thay bộ lọc reset về trang đầu, số trang tự co khi số dòng thay đổi. CSV giữ nguyên số âm, 0, null và escape chuỗi có nguy cơ được spreadsheet hiểu là công thức.
- Preview biểu đồ có request cancellation và revision guard. Sửa spec vô hiệu hóa preview cũ, kể cả phản hồi tới trễ; chỉ lưu được spec đã preview. Bỏ thay đổi chưa lưu cần xác nhận. Cột Y phải là số hoặc null, không ép chuỗi thành 0. Kết quả bị cắt 500 dòng có cảnh báo.
- Hỏi Claude có nút Dừng trả lời, Gửi lại câu hỏi, thời gian chờ và retry preview. Parser SSE xử lý UTF-8 bị chia chunk, CRLF, nhiều frame và frame bị đứt; không nhận event sai cấu trúc hoặc buffer quá lớn. Abort/ngắt kết nối phát tín hiệu tới worker, dừng CLI và nhả khóa phiên (đã test bằng process giả, chưa xác minh Claude thật).
- Khi reload giữa lúc lưu biểu đồ, giao diện bỏ trạng thái saving bị treo và nhắc kiểm tra Báo cáo của tôi: chưa biết lần lưu trước đã commit hay chưa. Không tự kết luận thất bại hay tạo lại. Bản chụp chỉ lưu khi mọi biểu đồ đề xuất đã preview thành công.
- Stderr CLI không được gom bằng blocking read hay trả nguyên văn ra UI. SSE vẫn báo lỗi/tool warning theo giao thức; unexpected exit có hướng dẫn kiểm đăng nhập/MCP. Các giới hạn tool, SQL, byte và row giữ nguyên.

Chạy unit frontend riêng: `npm --prefix webapp/web run test:unit`. `npm --prefix webapp/web test` chạy unit rồi tự dựng backend cho toàn bộ browser tests. Cần build trước vì browser kiểm đúng production bundle.
