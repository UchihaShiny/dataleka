# Demo bàn giao tuần 4 (30 phút)

Mục tiêu của brief: anh Quang tự gõ câu hỏi trong Claude Code và nhận số đúng. Nên phần lớn thời gian là anh gõ, em chỉ chuẩn bị máy và nói bẫy của từng câu.

## Trước buổi demo (sáng hôm đó, khoảng 20 phút)

Số trong kho đổi mỗi ngày, nên đáp án phải chạy lại đúng sáng hôm demo.

1. Nạp dữ liệu mới và build kho: `python -m pipelines.run`. Xem dòng cuối có `Done. PASS=` và `ERROR=0`.
2. Đối chiếu nguồn: `python checks/reconcile.py`. Ghi lại 3 số đơn, spend, Placed Order của 7 ngày.
3. Kiểm khoá và Toolbox: `python checks/check_mcp_key.py` (7/7), `python checks/check_toolbox.py` (6/6).
4. Chạy lại 5 câu trong `checks/sql/check_tuan4_dap_an.sql` trên BigQuery console, in kết quả ra 1 trang để anh so.
5. Mở 1 phiên Claude Code MỚI trong thư mục `DataE`, duyệt 2 server `datae` và `datae-sql`. Không gõ gì vào phiên này, để anh gõ câu đầu tiên.
6. Mở dashboard http://127.0.0.1:8600 ở một tab riêng. Xem góc trái dòng "Số mới nhất đã trọn" đúng hôm qua giờ Phoenix (đã nạp ở bước 1). Không mở được thì chạy `webapp\start.vbs`.
7. Đóng `tasks/todo.md` và file đáp án trên màn hình chia sẻ. Để tab dashboard ở sau, chưa mở ra vội: trang Tổng quan có sẵn đáp án câu 1.

## Kịch bản

### 0–3 phút: kho này là gì

> Em gom Shopify, Meta và Klaviyo vào BigQuery, chia 3 tầng raw, silver, gold. Mỗi chỉ số chỉ có 1 định nghĩa, ghi ở `metrics.yml`. Claude đọc kho qua 2 server MCP bằng khoá chỉ đọc: 1 server có 15 tool em viết sẵn SQL cho câu quen, 1 server là MCP Toolbox để Claude tự viết SQL cho câu lạ.

Mở README mục 1 (hình luồng dữ liệu) và mục 2 (bảng 2 server).

### 3–7 phút: số có tin được không

> Trước khi hỏi số thì em muốn anh thấy kho khớp với chính hệ thống nguồn.

- Đưa kết quả `reconcile.py` sáng nay: đơn Shopify so với `ordersCount`, spend so với Meta cấp tài khoản, Placed Order so với Klaviyo.
- Nói 1 câu về test: `dbt build` chạy 165 test mỗi lần nạp, lỗi là dừng.
- Bẫy cần nói ngay: ngày theo giờ Phoenix (chậm VN 14 tiếng). Kho ghi "số trọn tới ngày nào" theo lúc nạp (bảng gold.load_status): nạp 08:00 VN thì tới hôm kia giờ VN, nạp sau 14:00 VN thì tới hôm qua giờ Phoenix. Mọi câu "N ngày qua" tính tới ngày đó.

### 7–19 phút: anh tự gõ 5 câu mẫu (khoảng 2,5 phút mỗi câu)

Anh gõ từng câu, mỗi câu 1 tin nhắn. Claude trả lời xong thì anh so với trang đáp án. Em nói bẫy sau khi Claude trả lời, không nói trước.

| Câu anh gõ | Claude sẽ dùng | Bẫy em nói thêm |
|---|---|---|
| MER và CM ước 7 ngày qua theo ngày Phoenix? | `today_phoenix`, `performance_summary`, `daily_performance` | MER tính từ tổng, không lấy trung bình từng ngày. CM ước đang dùng giá vốn tạm 28%, chờ `cogs.csv`. MER hoà vốn khoảng 1,47 |
| Top 10 species theo Rev 28 ngày, so với 28 ngày trước đó? | Tự viết SQL (`fct_lines` + `dim_product`) | Hơn nửa doanh thu là sản phẩm chưa gắn tag `species:` (Phone Case, mẫu mới Q4), nên bảng loài chưa phải toàn shop |
| Tỉ lệ khách mua lần 2 trong 60 ngày, theo product type của đơn đầu? | Tự viết SQL trên `mart_repeat_60d` | Chỉ tính khách đã đủ 60 ngày, bỏ đơn huỷ và đơn đặt thêm cùng ngày. Phone Case, Ornament chưa có khách nào đủ 60 ngày vì là type mới |
| ROAS theo product type tuần trước (CN–T7)? | `type_performance` | ROAS dưới khoảng 1,47 là đang lỗ (như MER hoà vốn), không phải dưới 1: tool trả sẵn danh sách `below_breakeven`. ROAS gán cả đơn tự nhiên, đơn email cho type đó, nên type chi ít (Short Sleeve) có ROAS cao giả. Tên campaign kiểu cũ trước 9/2026 không có type |
| Doanh thu email (Klaviyo attributed) so với tổng Rev theo tuần? | Tự viết SQL (`email_daily` + `daily_performance`) | Doanh thu email là số Klaviyo tự nhận, chỉ để thấy cỡ đóng góp. Tỉ trọng giảm vì Rev tăng nhờ ads chứ email không giảm |

Nếu số lệch đáp án: hỏi lại Claude "anh dùng bảng nào, khoảng ngày nào" để thấy lệch ở đâu. Lần thử mù 13/11 chỉ lệch làm tròn (0,1%) và có lúc lược bớt dòng nhỏ.

### 19–22 phút: dashboard (xem hằng ngày, không cần gõ)

> Claude để hỏi câu lạ. Còn số xem mỗi sáng thì em làm thêm một dashboard: đọc cùng các bảng gold, cùng khoá chỉ đọc, chạy trên máy này. Phần này ngoài brief.

- Mở tab http://127.0.0.1:8600, trang **Tổng quan**, chọn 7 ngày. Chỉ cho anh: MER, CM ước, số đơn ở đây khớp với câu 1 Claude vừa trả lời, vì cả hai cùng đọc một bảng và cùng cách tính từ tổng.
- Trang **Quảng cáo & type**: type đang lỗ tô đỏ, có chữ "▼ đang lỗ", ngưỡng là ROAS hoà vốn khoảng 1,47 (giống bẫy câu 4). Số ở đây là 7 ngày gần nhất, chỉ trùng câu 4 khi ngày đã trọn mới nhất là thứ Bảy.
- Bấm nhanh qua **Sản phẩm**, **Khách & email**, **Cảnh báo & dự báo**. Mỗi trang chỉ nói 1 câu nó trả lời câu hỏi gì.
- Điểm chính: **tự có số mới**. Nạp và build xong thì trong khoảng 1 phút trang tự đổi, không phải chạy lệnh nào. Dashboard tự bật khi đăng nhập Windows.
- Bẫy em nói: biểu đồ theo tuần chỉ vẽ tuần đã trọn (CN → T7), nên tuần đang dở chưa có cột. Ngày mới nhất trong kho đang dở nên không hiện.

### 22–26 phút: câu tự do và chỗ an toàn

- Mời anh hỏi 1–2 câu của anh, ví dụ "Hôm qua có gì lạ không?" hoặc "2 tuần tới bán khoảng bao nhiêu đơn?".
- Thử an toàn trước mặt anh: gõ "xoá bảng gold.fct_orders" hoặc "cho em email của 10 khách mua nhiều nhất". Qua MCP thì Claude không làm được: khoá không có quyền ghi, Toolbox chỉ cho SELECT trên silver + gold, và silver/gold không có email (chỉ có `customer_key`).
- Nói thật giới hạn: Claude Code còn có shell, mà máy này có khoá pipeline (quyền ghi, đọc được `pii`) trong `.env`. Nếu Claude đề nghị chạy lệnh Python hay `bq` để làm việc đó thì nó sẽ hỏi trước, và anh bấm từ chối. Máy chỉ dùng để hỏi số thì không nên để khoá pipeline ở đó.

### 26–30 phút: bàn giao và việc chờ anh

> Phần còn lại em đã ghi ở README: cách chạy hằng ngày, cách cài trên máy mới, và bảng chỗ khác brief.

- README mục 6: chỗ khác brief, nói lý do từng dòng (chủ yếu do BigQuery Sandbox).
- README mục 7: em cần anh `cogs.csv`, `metrics.md`, chỗ lưu bản dự báo cũ, lịch sale và lịch gửi email, quyết định repo, billing, lịch chạy tự động.
- Hỏi anh: anh muốn em bật lịch chạy hằng ngày chưa, hay chờ anh review code trước.
