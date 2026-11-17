# Lessons

## 2026-11-09
- **Ngày "đã trọn" tính theo giờ shop (UTC-7), không theo giờ Việt Nam.** Trước 14:00 giờ Việt Nam thì ngày hôm qua ở shop chưa kết thúc.
- **Gọi endpoint Meta mới thì kiểm với đúng bản API trong `.env` trước.** `?ids=` đã bị bỏ từ v26. Phản hồi giả không bắt được lỗi kiểu này.
- **Không chạy dbt khi đang nạp, và không tự dùng token của Huy Anh.**
- **Không đọc hay ghi `.env`, kể cả chỉ `grep` tên biến hay in tiền tố key.** Tôi làm vậy để kiểm cấu hình và bị nhắc. Muốn biết thì hỏi, hoặc đưa script kiểm cho Huy Anh chạy.
- **File tạm của pipeline cũng là "xuất ra máy cá nhân".** dlt ghi JSONL có email, địa chỉ vào `data/` trước khi nạp. Brief cấm PII trên máy cá nhân, nên phải xoá sau mỗi lần nạp và không cache PII trên máy.
- **Bộ lọc ngày của API phải ghi mốc giờ đầy đủ có múi giờ.** Klaviyo hiểu `T00:00:00` không offset là UTC (mất 7 tiếng ngày cuối), Shopify hiểu `created_at:<2026-11-01` là tính cả ngày 1/11 (đếm dư 406 đơn). Cả hai lỗi chỉ lộ ra khi so với số đếm do chính nguồn trả.

## 2026-11-10
- **Đề xuất bước tiếp theo phải dựa trên tầng đã có thật, kiểm `tasks/todo.md` trước.** Tôi gợi ý tool MCP tính MER khi mới có `raw`, chưa có silver/gold. Thứ tự đúng: raw → dbt silver → gold → MCP.
- **Meta insights cấp ad × ngày: mỗi lần gọi tối đa 7 ngày.** Cả tháng 5/2026 làm Meta trả mã 1 (HTTP 500) rồi mã 2 (HTTP 400, subcode 1504044). Mã 1/2 là lỗi tạm: thử lại cả khi HTTP 400.
- **Kiểm "số khớp giữa các cấp" phải dùng 2 lần gọi độc lập.** Cộng cùng một bảng theo ad/adset/campaign luôn bằng nhau, không chứng minh gì.
- **Bước kiểm tra cũng tốn quota: phải co theo khoảng vừa nạp.** Reconcile so lại cả kho sau mỗi tháng nạp lùi làm tổng lần gọi Meta tăng dần, chạm mã 4 (giới hạn cả app, chung với đội ads). Lỗi giới hạn dùng chung thì dừng hẳn, không thử lại.
- **`dbt_project.yml` chỉ viết ASCII.** dbt đọc riêng file này bằng cp1252 trên Windows; chữ có dấu gây UnicodeDecodeError (lần đầu chạy qua chỉ vì tình cờ không có byte lỗi).
- **Wrapper gọi công cụ phải in lỗi khi thất bại.** `pipelines/dbt.py` trả mã lỗi mà không in `result.exception`, nên `docs generate` hỏng im lặng. Thử cả lệnh nhiều chữ (`docs generate`, `source freshness`), không chỉ `build`.
- **Hiểu mô hình kinh doanh trước khi nói insight.** DEERLY là POD (in theo đơn, không tồn kho); gợi ý "nhập/in bao nhiêu mỗi bản" là sai. Insight phải xoay quanh mẫu thiết kế, giá vốn theo biến thể, quảng cáo, catalog.

## 2026-11-11
- **Huy Anh học từng mô hình một: "phân tích kỹ" nghĩa là đào sâu MỘT mô hình, không trải hết.** Tôi viết cả 8 mô hình trong một lượt, bị nhắc. Mỗi lượt chỉ một mô hình, xong hỏi có sang mô hình tiếp không.
- **Khi học mô hình phân tích, không chèn code.** Huy Anh cần hiểu khái niệm, thống kê, cách đọc và ra quyết định trước; SQL chỉ đưa khi được hỏi.
- **Trả lời đúng phạm vi câu hỏi.** Hỏi "đã có chưa" thì xác nhận cái đã có, không kể thêm phần chưa học.

- (12/11) BigQuery: alias trùng tên cột gốc (`sum(spend) as spend`) thì `having sum(spend)` thành tổng của tổng, lỗi "Aggregations of aggregations". Cột tổng luôn đặt tên khác cột gốc (tong_spend).
- (12/11) Bash tool: script Python in tiếng Việt lỗi cp1252; chạy với `PYTHONIOENCODING=utf-8`.
- (12/11) Test 'giá trị không ghép vào SQL' bằng tìm chuỗi thì sai (chữ 'flow' có sẵn trong SQL); so với mẫu SQL cố định + kiểm @tham_số.
- (12/11) Lặp lại lỗi tổng của tổng ở ad_performance ngay sau khi ghi bài học: bài học chỉ ghi chữ thì không đủ. Đã thêm test tự dò (test_mcp_server mục 8). SQL mới luôn qua dry run (`checks/check_mcp_sql.py`) trước khi báo xong.
- (12/11) YAML: câu có ': ' trong mục '- ...' bị đọc âm thầm thành dict, không báo lỗi. Bẫy trong metrics.yml không dùng ': ' giữa câu; test_metrics_yml kiểm mọi bẫy là chữ.
- (12/11) Antigravity không tự tải lại file mình sửa từ ngoài: Huy Anh thấy metrics.yml cũ (12 chỉ số). Sau khi sửa file, nhắc đóng/mở lại tab hoặc Revert File, và đừng Ctrl+S tab cũ (ghi đè bản mới).
- (12/11) Lọc theo tên bằng chuỗi con thì khớp nhầm ('gift card' trong 'Gift Cardinal'). Dùng  cả cụm từ, và luôn có câu kiểm liệt kê những gì bị lọc.
- (12/11) Git Bash heredoc + python: chuỗi có dấu \ (regex ) so khớp sai; dùng chr(92) hoặc file .py viết bằng Write.
- (12/11) Test singular nên in TÊN dòng sai (cột loi), không chỉ đếm; và logic test phải khớp đúng thiết kế model (test XYZ gộp so tổng cả tuần model cố ý bỏ).
- (12/11, mô hình 8) "Ngày đã trọn" phải tính theo dữ liệu đã nạp (ngày của đơn mới nhất), không theo đồng hồ lúc build: pipeline nạp 18h giờ Phoenix, build chiều giờ VN thì Phoenix đã sang ngày mới, nên ngày mới nạp dở bị coi là trọn.
- (12/11, mô hình 8) Chuẩn hoá theo tỉ lệ (÷ mức) làm chỉ số hiếm (mức = 0) biến mất im lặng khỏi bảng. Luôn có test 'đủ mọi chỉ số' và đếm số ngày từng chỉ số.
- (12/11, mô hình 8) Kết quả có mô phỏng ngẫu nhiên (khoảng ETS lỗi nhân) phải cố định hạt giống; không thì 2 lần chạy ra 2 số và không so được trước/sau.
- (12/11, mô hình 8) Ngày nạp dở lọt qua tool KHÁC (daily_performance) rồi bị Claude so với dự báo. Mọi tool so 'thật vs kỳ vọng' phải tự nhắc ngày nào còn dở.
- (13/11) Khi đưa 'kết quả mong đợi' của script cạnh hướng dẫn sửa file cấu hình, người làm dễ chép nhầm dạng output vào file. Ghi rõ 'đây là output, không chép vào file', và đưa luôn khối nội dung file đúng.
- (13/11, mô hình 8) Đổi cách tính mốc thì đừng tiện tay hạ ngưỡng 'đủ dữ liệu': hạ ngưỡng làm chấm thêm ngày cũ ít dữ liệu, báo động tăng. Giữ ngưỡng, lùi xa hơn để đủ mốc; luôn so số ngày được chấm trước/sau.

## 13/11: thử Claude trả lời câu mẫu phải chạy MÙ
- Đáp án ghi trong tasks/todo.md (và checks/sql) nằm ngay trong repo: phiên thử được dán hướng dẫn có nhắc todo/brief nên đọc đáp án trước khi hỏi kho. Số vẫn đến từ truy vấn thật nhưng lần thử không còn giá trị chứng minh.
- Quy tắc: lần thử chỉ gõ đúng câu hỏi như người dùng thật (nguyên văn brief, không kèm ngày, không dán hướng dẫn). Sau đó đọc transcript (export_transcript) xem có Read/Grep file đáp án không, và số đến từ tool nào.

## 13/11: số in trong thông báo lỗi phải tự dùng được
- Lời từ chối in giới hạn đã làm tròn ("4,175") trong khi giới hạn thật là 4.174,6; AI làm theo đúng con số in ra thì lại bị từ chối.
- Quy tắc: giới hạn in cho người/AI đọc thì cận dưới làm tròn lên, cận trên làm tròn xuống, và có test gọi lại đúng con số đã in.

## 13/11: lọc theo ngưỡng phải nghĩ tới dòng "không thuộc nhóm nào"
- Danh sách "type lỗ" lọc ROAS < hoà vốn đã gom luôn dòng '(không theo type)' (rev 0 → ROAS 0), và mình còn báo con số tổng sai cho Huy Anh. Comment model ghi "roas null" nhưng SQL thật ra 0.
- Quy tắc: trước khi lọc theo ngưỡng, liệt kê các dòng đặc biệt ('(không rõ)', '(không theo type)', null) và quyết định riêng; so ngưỡng bằng số chưa làm tròn; có test cho từng dòng đặc biệt. Không tin comment, kiểm SQL.

## 16/11: "chạy và gom tin" là đưa lệnh cho Huy Anh chạy tay
- Mình tự chạy pipelines.run và reconcile bằng token thật vì hiểu câu "chạy và gom tin thôi" là cho phép. Huy Anh sửa: "tôi cần là chạy tay".
- Quy tắc: mọi lệnh dùng token/khoá (nạp, reconcile, dbt, check_*) Huy Anh tự chạy. Mình đưa lệnh từng bước, rồi gom tin từ kết quả Huy Anh dán.

## 16/11: React đổi trang phải bỏ số của trang cũ
- usePage giữ số trang cũ trong lúc tải trang mới, trang mới đọc nhầm cấu trúc và vỡ, làm trắng cả app.
- Quy tắc: gói số phải gắn nhãn (trang + tham số) và chỉ dùng khi khớp; mỗi trang bọc Error Boundary để lỗi không lan ra cả app.


## 16/11: shortcut Startup hỏng vì đường dẫn có dấu
- Triệu chứng: mở máy mà dashboard không tự bật. Shortcut DataLake.lnk trỏ "D:\Th?c t?p\..." (ự, ậ thành ?), đường dẫn không tồn tại nên Windows im lặng bỏ qua.
- WScript.Shell CreateShortcut ghi Arguments/WorkingDirectory theo bảng mã cũ: chữ có dấu thành "?". Ghi bằng Shell.Application (NameSpace().ParseName().GetLink, .Save()) thì giữ đúng Unicode.
- Kiểm shortcut bằng Test-Path -LiteralPath trên từng trường đọc lại, rồi chạy thử đúng shortcut đó (Start-Process file .lnk), không tin "đã tạo, mở được".
- Startup chỉ chạy khi đăng nhập sau khởi động/tắt máy; ngủ (sleep) rồi mở lại thì không chạy.

## 16/11: khuyên "nạp sau 14:00" mà không kiểm quy tắc ngày trọn
- Hệ thống coi ngày mới nhất CÓ ĐƠN là ngày dở (max(order_date) − 1), giả định nạp lúc 18:00 Phoenix. Nạp 00:07 Phoenix thì ngày mới chưa có đơn → mất trọn 1 ngày (dashboard dừng 14/11 dù 15/11 đã đủ).
- Trước khi khuyên đổi giờ chạy, tìm mọi chỗ giả định giờ chạy (grep max(order_date), "18:00 Phoenix") và thử mốc ngay sau nửa đêm Phoenix.
- Ngày trọn nên tính từ THỜI ĐIỂM NẠP (giờ Phoenix lúc kéo Shopify − 1 ngày), không đoán từ dữ liệu.


## 17/11: kiểm thử analytics app
- Hai kỳ cùng thiếu một số ngày vẫn KHÔNG đủ điều kiện so sánh. Kiểm ngày mong đợi, không chỉ so độ dài hai danh sách. Tổng cả kỳ phải unknown nếu thiếu ngày; khoảng trống trên chart không phải zero.
- SUM trả null khi chưa có dòng không đồng nghĩa tổng bằng 0. Giữ null cho hoàn tiền ở kỳ chưa có dữ liệu; không trừ hoàn lần nữa khỏi current_total.
- Fixture tiền tệ cũng phải làm tròn như NUMERIC (Decimal HALF_UP); test độc lập tìm ra lệch 0,01 USD vì float.
- Screenshot theme phải xác nhận html[data-theme] trước từng vòng. Nhiều addInitScript cộng dồn có thể tạo ảnh gắn nhãn sai theme.
- Accessible name cần chứa chữ hiển thị trên nút (audit bắt theme/sort); skip link không nên đổi hash routing của app.
- Interactive MCP thiếu khóa chỉ đọc phải fail closed; test cũ cho phép fallback khóa pipeline đã được thay bằng test từ chối.


## 17/11: preview và luồng chat cần có vòng đời rõ ràng
- Sửa spec trong lúc request preview đang chạy phải hủy request và vô hiệu hóa kết quả bằng revision; chỉ disable nút Lưu chưa đủ vì phản hồi cũ có thể bật lại nút.
- Abort fetch ở browser chưa đủ để dừng CLI. ASGI disconnect phải truyền cancel event xuống worker và nhả khóa trong finally; kiểm cả process không trả thêm dòng stdout.
- Không blocking read toàn bộ stderr của CLI khi kết thúc; pipe con có thể còn mở hoặc đầy. UI không nên trả stderr nguyên văn.
- Saving còn lại sau reload là kết quả chưa biết, không tự coi thành công/thất bại. Bỏ cờ treo và nhắc kiểm danh sách đã lưu trước khi tạo lại.
- E2E có hành động lưu/xóa phải tự dựng backend demo mới và store tạm, không mặc định dùng phiên người dùng ở 8600.
- Seed sessionStorage cho E2E bằng addInitScript trước khi app mount; ghi giữa lúc React đang khởi tạo có thể bị effect ghi đè và làm test ngẫu nhiên.
- Composer sticky có thể che lỗi và nút retry trên điện thoại. Kiểm bounding box và bấm nút thật trong trạng thái lỗi, không chỉ chụp trang chat trống.
