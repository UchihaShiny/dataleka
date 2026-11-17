# PROGRESS: DEERLY Data Lake (DataE)

Mỗi tối 3 dòng (theo brief): xong gì, vướng gì, mai làm gì. Chi tiết ở `tasks/todo.md`.

## 2026-11-16
- **Xong:** Huy Anh chạy tay lại `pipelines.run` + `reconcile` (OK, khớp nguồn; kho vẫn tới 14/11 Phoenix, spend 14/11 Meta chỉnh nhẹ 3.167,02 → 3.167,18). Lần đầu nạp 3 nguồn bằng `pipelines.run` (08:04 VN, cả 6 bước OK, dbt PASS=198 ERROR=0, dự báo mốc 14/11); reconcile 8–14/11 khớp cả 3 nguồn (Shopify 874 = 874, Klaviyo 874 = 874, Meta lệch 0,69 USD). Tuần 8–14/11: 874 đơn, rev 48.380, MER 1,98, CM ước 8.548 (tuần trước 815 đơn, MER 1,84, CM 6.128).
- **Thêm:** dashboard React + backend FastAPI trên máy (http://127.0.0.1:8600), đọc gold bằng khoá chỉ đọc, tự bật khi đăng nhập Windows, tự tải số mới sau khi nạp; số khớp tool MCP, 16 bộ test PASS.
- **Vướng:** 14/11 email không được gán đơn nào dù flow vẫn gửi (Welcome 604, Abandoned Checkout 43); có thể Klaviyo gán trễ, xem lại sau lần nạp tới. 13/11 hoàn 217,97 USD (mức để ý).
- **Mai:** chốt ngày demo bàn giao; báo anh Phone Case sát hoà vốn (ROAS 1,47) và AirPods Case lỗ (0,50, spend 1.335); 14 ngày tới có Thanksgiving, Black Friday, mô hình chưa biết sự kiện.

## 2026-11-13 (chiều): tuần 4
- **Xong:** mô tả đủ mọi bảng, cột silver + gold và đẩy lên BigQuery (trước 31% cột); bảng `mart_repeat_60d` cho câu mua lần 2; khoá `datae-mcp` đọc được silver qua authorized dataset (7/7); MCP Toolbox v1.16.0 là server thứ 2 `datae-sql`, chỉ SELECT trên silver + gold (6/6); Claude trả đúng 5 câu mẫu trong lần thử mù (không đọc file đáp án, câu 2, 3, 5 tự viết SQL); README bàn giao và kịch bản demo 30 phút.
- **Vướng:** khoá chỉ đọc chỉ chặn đường MCP, Claude Code vẫn có shell dùng được khoá pipeline nếu người dùng cho phép; số đáp án đổi mỗi ngày nên sáng hôm demo phải chạy lại.
- **Thêm (tối):** dashboard Streamlit trên máy (khoá chỉ đọc), 5 trang menu dọc bên trái: Tổng quan, Quảng cáo & type, Sản phẩm, Khách & email, Cảnh báo & dự báo; số khớp đáp án và tool MCP. Review độc lập code hôm nay ra 4 lỗi (type lỗ tính cả spend chưa gán type, so ROAS đã làm tròn, gợi ý sai khi spend quá thấp, so kỳ trước thiếu ngày), đã sửa kèm test, 15 bộ test PASS.
- **Mai:** chốt ngày demo bàn giao với anh Quang; chạy `pipelines.run` và chuẩn bị theo `docs/demo-ban-giao.md`; báo anh còn campaign tên kiểu cũ đang tiêu (~97 USD/tuần chưa gán type).

## 2026-11-13
- **Xong:** nạp + reconcile 5–11/11 khớp cả 3 nguồn (Shopify 802 = 802, Klaviyo 802 = 802, Meta lệch 0,15 USD); 2 type campaign mới từ 11/11 (Youth Hoodie → Hoodie, Ceramic Ornament → Ornament) đã thêm vào seed, dbt build ERROR=0; mô hình 8 phần dự báo xong (sai số tổng 14 ngày p80 khoảng 33%, tool từ chối kịch bản ngoài khoảng spend đã thấy) → đủ 5 mô hình; `pipelines.run` giờ chạy luôn dbt build và cập nhật dự báo.
- **Vướng:** chưa có chỗ lưu bản dự báo cũ (Sandbox xoá bảng sau 60 ngày, không MERGE) nên chưa chấm lại được dự báo; chưa có Q4 ở quy mô hiện tại, Black Friday 27/11 có thể lệch xa khoảng.
- **Mai:** chạy `pipelines.run` theo thứ tự mới lần đầu và kiểm log; thử lại 2 câu dự báo trong phiên mới (không ngoại suy, khoảng cho tổng 14 ngày).

## 2026-11-12
- **Xong:** nạp + reconcile 4–10/11 khớp cả 3 nguồn; tuần 3: `mart_daily_kpi` (AOV, CM ước), `mart_type_day` (spend theo type đọc từ tên campaign, ROAS theo type), `metrics.yml` một định nghĩa cho mỗi chỉ số, có bẫy và test; áp 5 mô hình phân tích, mỗi mô hình có bảng gold, chỉ số và tool MCP: Cohort (giữ khách theo tháng), RFM (9 nhóm, kiểm lại: Champions mua lại ~35%, Ngủ đông ~4%), CLV lịch sử (CAC ~34 USD), Pareto/ABC + XYZ (~17% mẫu làm ra 80% doanh thu), bất thường (`anomaly_check`, ~11,5% số ngày có báo động, đều giải thích được) và bước đầu dự báo (ETS 14 ngày tốt hơn cách đoán đơn giản ~17%); MCP từ 4 lên 15 tool, `metrics.yml` 29 chỉ số, 14 bộ test chạy qua.
- **Vướng:** anh Quang chốt bỏ so với `morning.html`, README ghi đối chiếu nguồn thay thế; tên campaign kiểu cũ (1–9/2026) không có type nên ROAS theo type chỉ có từ 10/2026; CM ước còn dùng giá vốn tạm 28%, chờ `cogs.csv`; chưa có lịch sale, lễ, ngày gửi campaign nên phần bất thường báo nhầm vào các ngày đó.
- **Mai:** kiểm cuối phần dự báo (dry run, thử tool trong phiên mới); hỏi anh `cogs.csv`, chỗ lưu bản dự báo cũ, lịch sự kiện.

## 2026-11-11 (ghi bù)
- **Xong:** gom lịch sử Meta, Klaviyo về 1/1/2026, mọi tháng khớp nguồn; nạp 9/11 trở đi; `dim_variant` (MagSafe/Standard, hoodie dày/thường) và `product_subline` theo tiền tố SKU (Sun Hoodie tách khỏi Long Sleeve); sửa lệnh dbt 2 chữ chạy im lặng; dọn script dùng một lần.
- **Vướng:** nghĩa nhiều tiền tố SKU là em suy từ tên sản phẩm, chờ anh duyệt `seeds/product_lines.csv`; tiền tố DL0, DL1 chưa rõ.
- **Mai:** tuần 3 (chỉ số chung, cổng khớp số); thêm tool MCP cho sản phẩm, ad, email, khách hàng.

## 2026-11-10
- **Xong:** gom lịch sử Meta, Klaviyo về 1/3/2026 (mỗi tháng khớp nguồn); khám phá schema 3 nguồn trên 1 ngày mẫu và viết phương pháp 4 bước; dbt silver + gold đủ checklist tuần 2 (star schema: dim_product, dim_customer, fct_orders, fct_lines, fct_ad_day; 108 test PASS; 1–7/11 ra 815 đơn, MER 1,84); MCP `datae` đọc gold, đã gọi thật ra đúng số.
- **Vướng:** app Meta chạm giới hạn chung (mã 4) lúc ~15:00, đã sửa để gọi ít đi và tự dừng; đang dừng gọi API theo lời anh Quang nên kho chưa có 9/11; còn chờ anh chốt ánh xạ SKU, metrics.md, COGS, khung giờ chạy, billing.
- **Mai:** nạp 9/11 trở đi và tháng 2, 1/2026 khi anh cho phép; thêm tool MCP cho sản phẩm, ad, email, khách hàng; demo tuần 2 bằng cách hỏi Claude trực tiếp.

## 2026-11-09 (ghi bù)
- **Xong:** BigQuery Sandbox, tầng raw 3 nguồn (Shopify 11.014 đơn khớp ordersCount, Meta, Klaviyo khớp số của nguồn), `pipelines.run` một lệnh, check_raw, reconcile, 8 bộ test, trang demo tuần 1.
- **Vướng:** báo cáo store ít hơn kho 11 đơn PAID; Sandbox không có MERGE và budget alert.
- **Mai:** gom lịch sử Meta, Klaviyo; demo tuần 1; hỏi anh billing, mốc lịch sử, file đối chiếu.


## 2026-11-17 — nâng cấp analytics app
- **Xong:** giao diện DEERLY’S responsive light/dark; khám phá campaign/sản phẩm với tìm kiếm, lọc, sắp xếp, phân trang, chi tiết và CSV aggregate; CLV lịch sử, metric dictionary từ metrics.yml và coverage gold có nhãn bằng chứng/unknown.
- **Xong:** demo cố định không credential, cùng hợp đồng pages/API, lưu demo riêng; live chart có preview/tạo/sửa/mở/xóa, snapshot giữ nguyên số; chat demo có nhãn và lưu riêng. Sửa thiếu ngày/null/NaN, không fallback khóa pipeline, không đổi theme làm mất hội thoại, kiểm forecast/cận/mốc cũ. Vite 7 vá vulnerability audit.
- **Kiểm tra:** baseline 15/16 suite Python PASS (Claude session validation phụ thuộc CLI); sau sửa 17/17 suite PASS, trong đó suite product có 12 regression. Build production, API và browser qua FastAPI được ghi trong docs/analytics-qa.md; không dùng test fixture làm bằng chứng live.
- **Giới hạn:** chưa gọi BigQuery/Claude/nguồn thật theo phạm vi an toàn của phiên; chưa có bằng chứng giờ nạp/đối soát từng nguồn từ gold. CM vẫn giá vốn tạm, CLV là doanh thu lịch sử. Không deploy, ingestion, reconcile hay bật lịch.


## 2026-11-17 — lượt nâng cấp 2
- **Xong:** bộ lọc/sắp xếp/phân trang khám phá có URL để mở lại; CSV giữ số âm và chống formula trong chuỗi. Preview có hủy request/revision guard, xác nhận bỏ sửa đổi, validate cột số và cảnh báo truncation.
- **Xong:** Hỏi Claude có dừng/gửi lại, thời gian chờ, retry preview; parser SSE đầy đủ và phục hồi trạng thái lưu dở. Backend truyền disconnect/cancel tới CLI, nhả khóa; giữ nguyên phạm vi tool chỉ đọc.
- **Kiểm tra:** thêm regression vòng đời chat, unit URL/CSV/SSE và browser race/recovery. Playwright tự dựng FastAPI demo ở 8601 với nơi lưu tạm, từ chối dùng lại server hiện có; không ghi vào preview/live.
- **Giới hạn:** lifecycle CLI kiểm bằng process giả và stream local, chưa dùng Claude thật hay BigQuery. Không sửa định nghĩa metric/model, không đọc .env hay kích hoạt ingestion/lịch.

- **Kết quả vòng cuối lượt 2:** 18/18 suite Python, 5 regression lifecycle, 4/4 unit JS, 14/14 browser PASS; build 460 modules, audit 0 vulnerability. Đã kiểm ảnh explorer desktop và chat lỗi mobile, sửa composer che retry; test seed storage sửa race và lặp riêng 3 lần PASS. Bằng chứng: docs/analytics-qa.md và docs/qa/browser-upgrade2-summary.json.


## 2026-11-17 — business pulse và bàn giao GitHub/Cloudflare
- Thêm hero tổng quan theo kỳ đang chọn, KPI từ cùng totals và nguồn/định nghĩa; nút làm mới có hành vi thực. Production build 461 modules, 4 unit JS + 14 browser tests PASS (kể cả axe và 4 viewport/2 theme).
- Chuẩn bị archive mã nguồn có manifest/checksum và scanner credential; script publish tạo deerlys-analytics PRIVATE trong tài khoản gh đã đăng nhập, không sửa repo gốc. Không kèm secrets, runtime, dữ liệu hay saved reports/analyses.
- GitHub connector chưa kết nối xong, gh chưa cài/đăng nhập, browser host không khả dụng: CHƯA tạo repo/push/mở dashboard. Chưa deploy. Dockerfile bàn giao chưa build vì không có Docker; chưa port Python Workers. Chi tiết docs/cloudflare-handoff.md.


## 2026-11-17 — dataleka private release
- Đích mới theo người dùng: UchihaShiny/dataleka PRIVATE, GitHub CLI chính thức đã xác thực tài khoản UchihaShiny. Giữ nguyên repo/index/origin DataLake.
- Refine phát hành: ZIP xác định có checksum từng file, quét credential cho mọi nội dung, loại runtime/PII lưu cục bộ, chặn symlink; tên dataleka thống nhất. Publish xác minh SHA main và private visibility. 4 regression offline PASS, gồm push Git bare local và kiểm repo gốc không đổi.
- Thêm workflow_dispatch kiểm Python, build và browser demo ở môi trường CI riêng; không tự chạy ingestion hoặc deploy. Lần chạy GitHub CI thực tế chưa được kích hoạt.
