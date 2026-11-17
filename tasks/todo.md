# DataE: dựng lại bằng BigQuery + dlt + dbt-core + MCP (2026-11-09)

Đã xoá toàn bộ bản cũ (DuckDB), chỉ giữ `.env` và `.env.example`. Mọi công cụ đều là open source hoặc free tier.

```text
Shopify (ShopifyQL) ┐                                load job
                    ├─ dlt ─→ Parquet trên máy (data/) ───────→ BigQuery raw ─→ dbt silver ─→ dbt gold ─→ MCP ─→ Claude
Meta Ads (Graph)    ┘
```

**BigQuery Sandbox (chốt 2026-11-09, vì chỉ là demo):** project `datae-514203`, không gắn thẻ. Sandbox không cho DML (`INSERT`, `MERGE`, `DELETE`) và streaming, bảng tự xoá sau 60 ngày. Vì vậy:
- dlt ghi ra Parquet trên máy (destination `filesystem`), không ghi thẳng vào BigQuery.
- Mỗi lần chạy lấy trọn khoảng ngày cần (mặc định 30 ngày đã trọn), rồi nạp vào BigQuery bằng load job `WRITE_TRUNCATE`, ghi đè cả bảng. Như vậy không có dòng trùng mà không cần MERGE.
- dbt chỉ dùng `view` và `table` (`CREATE OR REPLACE`), không dùng `incremental`.
- Hết 60 ngày bảng mất thì chạy lại.

## Kế hoạch (đã duyệt 2026-11-09)

### 1. Google Cloud (Huy Anh làm trên console, mình viết hướng dẫn)
- [x] Viết `docs/cai-dat-bigquery.md`: tạo project (Sandbox, không gắn thẻ), bật BigQuery API, tạo service account có 2 quyền `BigQuery Data Editor` và `BigQuery Job User`, tải khoá JSON vào `D:\Thực tập\DataE\secrets\` (đưa vào `.gitignore`).
- [x] Thêm vào `.env.example`: `GCP_PROJECT_ID`, `GOOGLE_APPLICATION_CREDENTIALS`, `BQ_LOCATION` (mặc định `US`).
- [x] Viết `checks/check_bigquery.py`: chạy `select 1` (giới hạn 10 MB), in project, location, số dataset; không in `private_key`. Đã thử 4 trường hợp lỗi: thiếu `.env`, thiếu file, sai loại khoá, khoá giả bị Google từ chối.
- [x] Huy Anh làm hướng dẫn trên console; `python checks/check_bigquery.py` ra OK (2026-11-09). Lần đầu 403 vì thiếu role `BigQuery Job User`, đã thêm.
- [x] Cài `dbt-bigquery` 1.12.2, `dlt[bigquery]` 1.32.0, `google-cloud-bigquery` 3.47.0; ghi `requirements.txt`, `.gitignore` (có `secrets/`).

### 2. dlt lấy dữ liệu ra Parquet, rồi nạp vào dataset `raw`
- [x] `pipelines/sources/shopify.py`: các resource `sales_daily`, `sales_by_product_daily`, `sales_by_channel_daily`, `sessions_daily` gọi ShopifyQL như bản cũ. Không dùng nguồn Shopify có sẵn của dlt, vì nó cần quyền đơn hàng mà token không có. (13/11 rà: thay bằng bulk orders/products trong shopify.py)
- [x] `pipelines/sources/meta.py`: `campaign_insights_daily`, `ad_insights_daily`, `ads` (đọc qua `act_X/ads`, lọc `id IN`, không dùng `?ids=` vì v26+ đã bỏ). Token chỉ để trong header. (13/11 rà: xong: ad_insights_daily, ads)
- [x] dlt destination `filesystem` (Parquet ở `data/`), `write_disposition="replace"`; khai khoá chính để dbt test được. (13/11 rà: thay: JSONL vì pyarrow Parquet bị Application Control chặn)
- [x] `pipelines/load_bigquery.py`: nạp từng file Parquet vào `raw` bằng load job `WRITE_TRUNCATE`, kiểm số dòng sau khi nạp bằng số dòng trong file. Không dùng DML. (13/11 rà: thay: load job nằm trong pipelines/common.py)
- [x] `--until` chỉ nhận ngày đã kết thúc theo giờ shop (UTC-7). (13/11 rà: xong: pipelines/dates.py chỉ nhận ngày đã trọn)
- [x] `pipelines/run.py`: chạy dlt, nạp BigQuery, rồi `dbt build`, bước nào lỗi thì dừng. Gọi dbt qua `python -c` vì `dbt.exe` bị Application Control chặn. (13/11 rà: xong; 13/11 run.py chạy cả dbt build + forecast.publish)

### 3. dbt-core + dbt-bigquery
- [x] Cài `dbt-bigquery` bằng `python -m pip`. Dùng profile kiểu `service-account`, đọc đường dẫn khoá từ env. (13/11 rà: xong)
- [x] Silver: `stg_*` đổi kiểu, tách `actions` của Meta (chỉ lấy `purchase`, không cộng `omni_purchase`). (13/11 rà: xong)
- [x] Gold: `daily_performance` (đơn, `net_sales`, sessions, spend, MER, ROAS Meta, CR), `campaign_performance`, `ad_performance` (CTR, CPM, tuổi mẫu), `product_performance`. (13/11 rà: xong, tên bảng khác kế hoạch đầu: daily_performance, fct_*, dim_*, mart_*)
- [x] Test: khoá duy nhất, not_null, và một test so tổng spend theo ad với số theo chiến dịch. (13/11 rà: xong, nay PASS=152)
- [x] Bảng Gold `partition_by` theo `date`, để truy vấn quét ít dữ liệu. Chỉ dùng `view`/`table`, không `incremental` (Sandbox không có MERGE). (13/11 rà: bỏ: Sandbox, bảng nhỏ, quét < 4 MB mỗi câu)

### 4. MCP server
- [x] `mcp_server/server.py` (mcp 2.x, `MCPServer`) đọc Gold trên BigQuery: tổng quan theo khoảng ngày, theo ngày, chiến dịch, mẫu quảng cáo, sản phẩm, định nghĩa chỉ số. Lỗi phải raise `ToolError`. (13/11 rà: xong, nay 15 tool)
- [x] Mỗi truy vấn đặt `maximum_bytes_billed` để không thể vượt free tier. (13/11 rà: xong: MAX_BYTES 200 MB)
- [x] `.mcp.json` để Claude Code nạp server. (13/11 rà: xong)

### 5. Kiểm tra
- [x] Test không token: nguồn dlt với phản hồi giả (phân trang, chạy lại không trùng, từ chối ngày chưa trọn). (13/11 rà: xong, 14 bộ test)
- [x] Thử sớm trên Sandbox thật: một bảng nhỏ đi đủ đường Parquet → load job → dbt table. Nếu Sandbox chặn bước nào thì dừng, lên kế hoạch lại. (13/11 rà: xong)
- [x] Huy Anh chạy lần đầu với 7 ngày đã trọn (1/11 đến 7/11), đối chiếu với số đã chốt trước khi xoá: 1–7/11 có 815 đơn, `net_sales` 41.175,73, spend 24.098,90. (13/11 rà: xong)
- [x] Khớp rồi mới nạp thêm 10/10 đến 8/11. (13/11 rà: xong)
- [x] Gọi thử từng tool MCP, số khớp với truy vấn BigQuery trực tiếp. (13/11 rà: xong, nhiều lần)

## Nguyên tắc
- Mình không chạy lệnh dùng token Shopify, Meta hay khoá GCP khi chưa được Huy Anh đồng ý. Sửa xong thì test bằng phản hồi giả, rồi đưa lệnh cho Huy Anh chạy.
- Không cài tool SaaS trả phí.


## Tuần 1 theo brief DEERLY Data Lake (Raw/Bronze), chạy trên BigQuery Sandbox

Brief: https://claude.ai/artifact/418ir3XufvNCGnrVs1mBLP. Sandbox: nạp full bằng load job ghi đè thay cho incremental MERGE; không partition theo ngày kinh doanh; không budget alert.
Token Shopify đủ quyền (2026-11-09): `read_orders`, `read_all_orders`, `read_products`, `read_customers`.

- [x] Project `datae-514203`, BigQuery API, service account, kiểm kết nối OK.
- [x] Dataset `raw`, `silver`, `gold`, `pii` (US).
- [~] Budget alert $10: không áp dụng trên Sandbox.
- [x] 1. Khung `pipelines/common.py`: dlt → JSONL (`data/`) → gộp file → 1 load job `WRITE_TRUNCATE` mỗi bảng, schema lấy từ dlt → so số dòng. Đổi từ Parquet sang JSONL vì Application Control chặn DLL Parquet của pyarrow. `tests/test_common.py` PASS; `checks/try_sandbox.py` trên Sandbox thật: 2 lần nạp vẫn 100 dòng/100 id, 200 dòng bảng con, tổng NUMERIC đúng 5049, kiểu TIMESTAMP/DATE/NUMERIC/BOOLEAN đúng; đã xoá bảng thử.
- [x] 2. dlt Shopify (`python -m pipelines.load_shopify`, 2026-11-09): raw.shopify_orders 11.014, order_line_items 16.972, order_refunds 114, products 4.599, product_variants 95.846; pii.shopify_customers 9.077. Khoá trùng 0, đơn từ 2024-11-01. Raw không có cột PII.
- [~] 3. (Huy Anh không có quyền vào Shopify Admin của DEERLY. Thay bằng `reconcile.py`: 11.014 = ordersCount, 0/19 tháng lệch. Còn: nhờ anh mở Admin so 1–2 tháng trong buổi demo.) Demo: `checks/demo_orders_by_month.py` ra bảng theo tháng. Đối chiếu độc lập với số ShopifyQL đã khớp Admin trước đây: 28/10–3/11 = 809 đơn, 1–7/11 = 815, 10/10–7/11 = 3.226, khớp đúng. Còn: Huy Anh so vài tháng với Shopify Admin.
- [x] 4. dlt Meta: chạy thử 7 ngày (1–7/11) OK: raw.meta_ad_insights_daily 1.509 dòng, 313 ad, 35 campaign, spend 24.098,67 (số đã chốt trước 24.098,90, lệch 0,23 ở 1/11 do Meta cập nhật muộn); raw.meta_ads 2.795 ad, phủ hết ad trong insights. Bỏ tham số effective_status vì Meta v27 trả 400. Không chạy 13 tháng một lần. Chiều 9/11 Huy Anh nạp dần mỗi tiếng một tháng bằng `--since/--until`, lùi từ tháng 10/2026.
- [x] 5. dlt Klaviyo 7 ngày (1–7/11): campaigns 53 (đủ tên), campaign_messages 53, flows 11, metrics 72, message_daily 480. Placed Order 786 đơn (Shopify 815), attributed email 2.525,80 trên ~44.371 Rev. Revision mới: bỏ filter messages.channel, trường nằm trong `definition`, làm tròn tiền 2 chữ số. Còn: nạp dần lịch sử từng tháng.
- [x] 6. Chạy lại lần 2 (9/11, 06:40 UTC): khoá trùng 0 ở cả 13 bảng. Orders 11.014, line items 16.972, refunds 114, khách 9.077, Meta 1.509/2.795, Klaviyo 53/53/11/72/480 giữ nguyên. Products tăng 4.599 → 4.696 và variants 95.846 → 100.379: đúng bằng 97 sản phẩm, 4.533 variant tạo mới giữa 2 lần nạp (kiểm theo created_at).
- [x] Đọc từ khoá 1–4 (Modern Data Stack, ELT, Cloud Warehouse, Medallion), nối với phần đã làm (9/11).
- [x] Cuối ngày ghi báo cáo / `PROGRESS.md`. (13/11 rà: xong)

## Kiểm soát limit (2026-11-09, đã làm)

- [x] Meta (Dev tier: Ads Insights 600 + 400 × số ad đang chạy mỗi giờ/tài khoản; điểm cả app tối đa 60, hồi 300 giây). `pipelines/sources/meta.py`:
  - giãn tối thiểu 15 giây giữa 2 lần gọi (siết lại vì token chung app với đội ads, anh xác nhận);
  - đọc `x-business-use-case-usage`, `x-ad-account-usage`, `x-fb-ads-insights-throttle`, `x-app-usage`: ≥ 50% chờ (theo `estimated_time_to_regain_access`, tối thiểu 60 giây), ≥ 75% dừng hẳn, không ghi BigQuery;
  - bị chặn (mã 4/17/32/613/80000/80004) thì chờ đủ 300 giây;
  - 1 lần `me/adaccounts` kèm spend → chỉ gọi insights cho tài khoản có spend (bỏ 7 tài khoản rỗng);
  - cây ad cache 24 giờ ở `data/meta_cache/ads.json`.
- [x] Meta, Klaviyo: tự từ chối trong giờ làm việc Phoenix 8–17h (22:00–07:00 giờ Việt Nam), trừ `--force`; mỗi lần tối đa 31 ngày; bỏ `--backfill-months`.
- [x] Shopify: đọc `extensions.cost.throttleStatus`, còn dưới 20% điểm thì chờ hồi tới 50%.
- [x] Klaviyo: giãn 0,5 giây giữa các lần gọi, giữ chờ theo `Retry-After`.
- [x] BigQuery: `check_raw.py` in dung lượng (37,7 MB / 10 GB), cảnh báo > 8 GB. Đo truy vấn tháng cần quyền `bigquery.jobs.list` (service account chưa có) nên tạm bỏ qua; mọi truy vấn vẫn có `maximum_bytes_billed`.
- [x] Sổ `logs/limits.jsonl`: mỗi lần chạy ghi nguồn, khoảng ngày, số lần gọi, mức dùng cao nhất, số lần và số giây chờ.
- [x] Test: `tests/test_limits.py` PASS (đọc header, giãn 15 giây, 60% chờ, 80% dừng, mã 17 chờ 300 giây, Shopify chờ hồi, chặn giờ Phoenix, tối đa 31 ngày, ghi sổ). 4 test cũ vẫn PASS. Test ghi sổ vào thư mục tạm, không đụng sổ thật.
- [x] Chạy thật lần đầu (9/11, 07:04 UTC, 2–8/11): 10 lần gọi (trước ~35), mức dùng cao nhất 3%, không phải chờ. Chỉ 1/8 tài khoản có spend. Insights có 1–8/11 = 1.730 dòng; meta_ads 2.546 (chỉ tài khoản có spend; phủ đủ ad trong insights, tài khoản khác được thêm khi nạp tháng cũ có spend ở đó). Sổ `logs/limits.jsonl` đã ghi.
- [x] Chưa làm: dbt profile `maximum_bytes_billed` (tuần 2, khi dựng dbt). (13/11 rà: xong: profiles.yml maximum_bytes_billed)

Review: đã chạy thật, cú pháp `insights.time_range({...}){spend}` hoạt động.

## Nạp tháng 10/2026 (9/11)
- [x] Meta: 5.759 dòng mới, 13 lần gọi, mức dùng cao nhất 3%, không chờ; cây ad dùng cache. Bảng có 1/10–8/11 = 7.489 dòng, mọi ad đều có trong meta_ads. Spend tháng 10 = 80.249,72. Spend 10/10–7/11 = 89.674,34, số đã chốt trước là 89.675,39 (lệch 1,05, tức 0,001%).
- [x] Klaviyo: 2.065 dòng mới, 7 lần gọi; message_daily 1/10–7/11 = 2.545 dòng. Placed Order theo tuần khớp đúng số đơn Shopify các tuần 4/10 (518), 11/10 (752), 18/10 (802); tuần 25/10 là 719 so với 748, tuần 1/11 là 786 so với 815. Doanh thu attributed email chiếm 5–9% Rev.
- [ ] Huy Anh so spend tháng 10 (80.249,72) với Ads Manager.

## Kế hoạch: làm kỹ tuần 1 (2026-11-09, chờ Huy Anh duyệt)

Mục tiêu: tầng raw đủ, đúng, chạy một lệnh, chứng minh bằng số độc lập, trước khi sang dbt.

- [x] A. (`pipelines/run.py`, `tests/test_run.py` PASS) Một lệnh chạy cả tuần 1: `python -m pipelines.run`. Gồm Shopify, Meta, Klaviyo, rồi `check_raw`. Bước nào lỗi thì dừng. Mỗi lần ghi `logs/runs.jsonl` (bước, thời gian, số dòng, mức dùng quota). Tôn trọng giờ Phoenix và quota như từng lệnh lẻ.
- [x] B. (9/11: Shopify trễ 4 giờ, Meta 1 giờ, Klaviyo 25 giờ; `tests/test_dates.py` PASS) Freshness theo brief (data mới trong vòng 36 giờ): `check_raw` báo ngày mới nhất của từng nguồn so với ngày đã trọn theo Phoenix. Trễ quá 36 giờ thì báo lỗi.
- [x] C. (Shopify ✓ 11.014/11.014, 0/19 tháng; Klaviyo ✓ 3.945/3.945, 0/39 ngày; Meta 39 ngày: nguồn 107.803,46, kho 107.802,00, lệch 0,001%; 2 ngày vượt ngưỡng 0,01%: 8/10 −0,31, 23/10 −0,52; chẩn đoán: cấp ad gọi lại bằng kho (±0,03), còn tổng cấp ad thấp hơn cấp tài khoản ngay tại Meta (0,34; 0,53). Không phải lỗi pipeline; ngưỡng Meta ≤ 1 USD/ngày, ghi trong docs) Đối chiếu với số đếm do chính nguồn trả, thay cho so tay:
  - Shopify `ordersCount` theo từng tháng (cùng bộ lọc với Admin) so với `raw.shopify_orders`. Mỗi tháng 1 lần gọi nhẹ.
  - Meta spend cấp tài khoản theo ngày (1 lần gọi mỗi tháng) so với tổng spend cấp ad.
  - Klaviyo: số campaign, số flow so với danh sách.
  Lệch thì in tháng/ngày lệch.
- [x] D. (chạy thật 9/11 07:46 UTC: mốc 2026-11-09 06:32 − 1 ngày, lấy 442 đơn sửa, gộp xong vẫn 11.014 đơn, khoá trùng 0, 12 lần gọi, mức dùng 1%. Code + test giả PASS: đơn sửa, đơn mới, đơn cũ trước 2024-11 bị bỏ kèm khách; bản cũ đọc từ BigQuery bằng list_rows; xoá JSONL có PII sau mỗi lần nạp; chờ chạy thật) Shopify incremental theo `updated_at` đúng như brief: lần đầu lấy full, các lần sau bulk chỉ lấy đơn có `updated_at` từ lần chạy trước trừ 1 ngày. Gộp vào bản lưu trên máy theo `order_id` (thay cả line items, refunds của đơn đó), rồi mới ghi đè BigQuery. Sandbox vẫn không cần MERGE. Test: đơn sửa, đơn huỷ, đơn hoàn tiền sau.
- [x] E. (chạy lại 9/11 07:52 UTC: 38 flow message, khoá trùng 0. Trước đó: 40 dòng nhưng 2 message trùng do A/B test nằm dưới 2 action; đã gộp theo message_id, cột `action_ids`; cache 24 giờ vì đi hết flow tốn ~90 lần gọi. Chờ chạy lại để xác nhận) Klaviyo flow messages: lấy flow → flow-actions → flow-messages (11 flow) để nối `message_id` trong `message_daily` về flow. Hiện chỉ nối được campaign.
- [x] F. `docs/raw-tables.md`: từ điển bảng raw (mỗi bảng: nguồn, khoá, cột chính, cách nạp, bẫy đã biết).
- [x] G. Nạp dần lịch sử Meta, Klaviyo mỗi tiếng một tháng (Huy Anh chạy). (13/11 rà: xong: lịch sử về 1/1/2026)
- [x] H. Demo: số đơn theo tháng khớp Shopify Admin. Sau C thì có thêm bảng so tự động với `ordersCount`. (13/11 rà: xong: docs/demo-tuan-1.html)

Thứ tự đề xuất: B → A → C → D → E → F. G chạy song song.

Review (9/11): 8 bộ test đều PASS. Phát hiện và sửa: dlt để JSONL có PII trong `data/shopify/` trên máy, trái brief; đã xoá và cho tự xoá sau mỗi lần nạp. `check_raw` sẽ báo thiếu `raw.klaviyo_flow_messages` cho tới lần chạy Klaviyo tiếp theo.

## Đối chiếu lần đầu (9/11, `reconcile.py --only shopify klaviyo`)
- [x] Klaviyo lệch 30/9 (+12) và 31/10 (−29): bộ lọc datetime không có múi giờ nên Klaviyo hiểu là UTC, trong khi nhóm ngày theo Phoenix, nên ngày cuối mỗi khoảng mất 7 tiếng. Đã thêm `-07:00` vào bộ lọc (pipeline và reconcile), test kiểm offset. Cache Klaviyo cũ sai ở ngày cuối mỗi khoảng.
- [x] Nạp lại Klaviyo tháng 10 và 1–8/11 với bộ lọc đúng: reconcile ✓ Placed Order 3.945 = 3.945, 0/39 ngày lệch.
- [x] Shopify: ordersCount 11.420 so với kho 11.014. Chẩn đoán tháng 10: 137 đơn "thiếu" đều tạo ngày 1/11 giờ Phoenix (ngày 1/11 có đúng 137 đơn). Shopify search `created_at:<2026-11-01` (chỉ ghi ngày) tính luôn ngày 1/11, nên script đối chiếu đếm dư ngày đầu mỗi tháng sau. Kho không thiếu đơn. Đã đổi reconcile, diagnose và mốc lịch sử của pipeline sang mốc giờ đầy đủ `-07:00`. Chạy lại 9/11: ✓ 11.014 = 11.014, 0/19 tháng lệch.

## So với báo cáo store (Shopify Reports, ảnh Huy Anh gửi 9/11)
Lưu lại ở `docs/reference/store-report-orders-by-month.csv`.
- Khớp đúng từng đơn 8/11 tháng (01–07/2026, 11/2026). REFUNDED và PARTIALLY_REFUNDED khớp mọi tháng.
- Lệch chỉ ở PAID: 08/2026 kho nhiều hơn 9, 09/2026 và 10/2026 mỗi tháng nhiều hơn 1. Tổng 11 tháng: báo cáo 10.836, kho 10.847, lệch 11 (0,1%), dưới ngưỡng 1% của brief.
- Kho khớp tuyệt đối với `ordersCount` (danh sách Orders), nên báo cáo store đang bỏ qua 11 đơn theo một quy tắc chưa biết.
- Đã loại trừ: processed_at khác tháng (0 đơn), đơn test (0), đơn nháp 0 đồng (tháng 4, 5 có mà vẫn khớp), một nguồn bán riêng lẻ.
- [ ] Câu hỏi mở: cần danh sách mã đơn PAID tháng 8 từ báo cáo store, câu ShopifyQL của báo cáo, hoặc quyền `read_reports`, để tìm đúng 11 đơn. Cần trước cổng khớp số tuần 3.
- [x] Meta 7 ngày qua `pipelines.run` (9/11 08:19 UTC): 4 lần gọi, mức dùng 2%, cây ad dùng cache.

## Review tuần 1 (9/11, 15:30)
Tầng raw đủ, đúng, chạy một lệnh, đã chứng minh bằng số của chính nguồn:
- Shopify ✓ 11.014 = ordersCount, 0/19 tháng lệch. Klaviyo ✓ 3.945 = 3.945 Placed Order, 0/39 ngày. Meta ✓ 0,001%, mọi ngày lệch < 1 USD (do Meta làm tròn cấp ad). Báo cáo store: khớp 8/11 tháng, lệch 11 đơn PAID (0,1%), chờ dữ liệu từ anh.
- `python -m pipelines.run` chạy cả 3 nguồn + `check_raw` (đủ bảng, khoá trùng 0, độ mới < 36 giờ). Shopify incremental theo updated_at. Chạy lại không trùng.
- Quota Meta: 4–13 lần gọi, mức dùng cao nhất 3%; chặn giờ Phoenix; sổ `logs/limits.jsonl`.
- PII chỉ trong dataset `pii`, file tạm có PII tự xoá.
- 8 bộ test PASS. Từ điển bảng `docs/raw-tables.md`.
- Lỗi tìm ra nhờ đối chiếu: bộ lọc ngày Klaviyo hiểu theo UTC, Shopify `created_at:<ngày` tính cả ngày đó; flow message trùng do A/B test.
Còn: nạp dần lịch sử Meta/Klaviyo trước 1/10; demo với anh (nhờ anh xem Admin 1 tháng); câu hỏi billing, Meta 13 tháng, file đối chiếu của anh, repo, 11 đơn báo cáo store.

## Ngày mai 2026-11-10: phần tuần 1 còn lại

Nạp dần lịch sử (chạy trong 07:00–22:00 giờ Việt Nam, cách nhau ≥ 1 tiếng, mỗi lần 1 tháng):
- [x] Tháng 9 (9/11 16:29 giờ VN): Meta 2.544 dòng, 30 ngày, spend 38.120,84, 7 lần gọi, mức dùng 1%; Klaviyo 1.110 dòng, 30 ngày. check_raw OK. Lần chạy đầu lúc 16:18 im lặng hơn 8 phút (chữ bị giữ trong bộ đệm của tiến trình con, đã sửa bằng PYTHONUNBUFFERED; vì sao chạy lâu thì chưa rõ), đã Ctrl+C và chạy lại.
- [x] Tháng 8 (10/11 08:06 giờ VN): Meta 2.422 dòng, 6 lần gọi, mức dùng 1%; Klaviyo 1.251 dòng. Meta, Klaviyo giờ có 1/8–8/11. check_raw OK.
- [x] Shopify incremental 10/11 08:12: lấy 783 đơn sửa, gộp xong 11.102 đơn (+88 đơn mới), 17.109 line item, 9.144 khách, đơn mới nhất 01:01 UTC 10/11. check_raw OK.
- [x] Tháng 7 (10/11 09:10 giờ VN): Meta 5 lần gọi, mức dùng 1%, ad_insights_daily lên 14.119 dòng; Klaviyo 7 lần gọi, message_daily 5.960. check_raw OK. Reconcile 10:03: Meta ✓ 1/7–8/11 spend 237.545,54 vs kho 237.543,16, 0/131 ngày lệch quá 1 USD; Klaviyo ✓ Placed Order 8.383 = 8.383.
- [x] Tháng 6 (10/11 10:13 giờ VN): Meta 8 lần gọi, mức dùng 3%, ad_insights_daily 16.552, ads 2.570; Klaviyo message_daily 6.396. check_raw OK. Reconcile 10:21: Meta ✓ 1/6–8/11 spend 267.373,04 vs kho 267.370,65, không ngày nào lệch quá 1 USD; Klaviyo ✓ 9.505 = 9.505, 0/161 ngày.
- [~] Tháng 5 lần 1 (10/11 ~11:15 giờ VN): Meta lỗi mã 1 ×3 (HTTP 500) rồi mã 2 (HTTP 400, subcode 1504044) ở act_918678220936371/insights, dừng trước khi ghi, không mất dữ liệu. Sửa: insights gọi theo đoạn ≤ 7 ngày trong từng tháng (`dates.weeks`), mã 1/2 hoặc `is_transient` thì thử lại cả khi HTTP 400. 8 bộ test PASS (thêm test mã 1/2 thử lại, mã 100 dừng ngay).
- [x] Tháng 5 chạy lại (10/11 11:29 giờ VN) với code chia tuần: Meta 6 lần gọi (1 tài khoản + 5 đoạn 7 ngày), mức dùng 3%, không phải thử lại; ad_insights_daily 17.635 (+1.083), spend tháng 5 = 17.105,34. Klaviyo message_daily 6.427. check_raw OK. Reconcile 11:37: Meta ✓ 1/5–8/11 spend 284.478,38 vs kho 284.475,94; Klaviyo ✓ 10.077 = 10.077, 0/192 ngày.
- [x] Tháng 4 (10/11 13:52 giờ VN): Meta 6 lần gọi, 3%, ad_insights_daily 18.587 (+952); Klaviyo message_daily 6.457. check_raw OK, reconcile 13:56 (Meta 17 lần gọi, 4%).
- [~] Tháng 3 (10/11 14:54 giờ VN): đã nạp (Meta 30 lần gọi, 3%; Klaviyo 98 lần gọi, 2 lần chờ 429). Reconcile 15:31 giờ VN bằng code mới (Meta 5 lần gọi, 3%): Meta ✓ spend tháng 3 = 2.919,53, khớp đúng; Klaviyo ✓ Placed Order 98 = 98. Tháng 3 rất thấp so với tháng 4–10 (spend 17–38k/tháng): cả 2 nguồn cùng thấp và khớp nguồn, nên là hoạt động thật của shop chứ không phải thiếu dữ liệu.
- [x] **Mốc lịch sử chốt (Huy Anh, 10/11): Meta, Klaviyo chỉ gom tới 1/2026.** Còn đúng 2 tháng: 2/2026 và 1/2026. Vẫn tạm dừng tới khi anh Quang báo xong việc (agent của anh gọi Meta nhiều). Mỗi tháng: `pipelines.run --skip shopify --since … --until …` rồi `reconcile --only meta klaviyo --since … --until …`, cách nhau ≥ 1 giờ. Shopify giữ nguyên từ 11/2024 (đã có, không tốn quota chung). (13/11 rà: xong: đã gom đủ tới 1/2026)
- [~] (thay bằng dòng mốc 1/2026 ở trên) (xem câu hỏi Meta 13 tháng): `python -m pipelines.run --skip shopify --since 2026-07-01 --until 2026-07-31`. Sau mỗi tháng: `check_raw` OK, `reconcile --only meta` OK.
- [x] (10/11, kiểm trên cache, không gọi API) Cây ad đủ cho mọi tài khoản có spend: 918678220936371 (3–11/2026), 3 tài khoản chỉ chạy tháng 3 (3949189065379139, 1591372612312756, 2102201770509698) và 1761272655041104 (tháng 6) đều có trong `meta_ads`. Còn 51 dòng insights của tài khoản chính (5–9/2026) có ad_id không có trong cây ad: nhiều khả năng ad đã xoá (edge /ads không trả ad đã xoá); tên campaign/adset/ad vẫn có trong insights.

Demo tuần 1 với anh Quang (15 phút):
- [ ] Chạy `python -m pipelines.run` và `python checks/reconcile.py` trước mặt anh.
- [ ] Nhờ anh mở Shopify Admin → Orders, lọc 10/2026: kho ra 3.016 đơn (3.011 nếu bỏ đơn huỷ).
- [ ] Nói rõ 3 chỗ khác brief: không đặt được budget alert (Sandbox), ghi đè cả bảng thay MERGE (Sandbox), Klaviyo lấy số đếm ngày × message thay event thô.

Hỏi anh (chặn tuần 2–3):
- [ ] Billing Google Cloud gắn tài khoản nào? Có chuyển khỏi Sandbox không (để có MERGE, partition, budget alert)?
- [x] Meta cần bao nhiêu tháng lịch sử? → Huy Anh chốt 10/11: tới 1/2026.
- [ ] File để làm cổng khớp số: `dashboard/morning.html`, `scripts/morning.py`, `context/metrics.md`, `context/cogs.csv` lấy ở đâu?
- [ ] 11 đơn PAID báo cáo store ít hơn kho (8/2026: 9, 9/2026: 1, 10/2026: 1): xin danh sách mã đơn, câu ShopifyQL, hoặc quyền `read_reports`.
- [ ] Quyền xem Shopify Admin của DEERLY (để tự kiểm số).
- [ ] Repo đặt ở đâu, ai review code?
- [ ] (Nhỏ) Thêm quyền `bigquery.jobs.list` cho service account để đo lượng truy vấn trong tháng?

Tự học từ code tuần 1 (để trả lời được khi demo):
- [ ] Đọc `pipelines/common.py`: vì sao gộp file rồi 1 load job `WRITE_TRUNCATE`.
- [ ] Đọc `pipelines/sources/shopify.py`: `watermark`, `merge` (đơn sửa thay line items thế nào).
- [ ] Đọc `pipelines/sources/meta.py`: `usage`, `respect`, `ad_accounts` (vì sao chỉ dùng 3% quota).

Cuối ngày:
- [x] Ghi `PROGRESS.md` (10/11 tối, kèm bù 9/11).

## Trang demo tuần 1 (9/11)
- [x] `checks/demo_page.py` sinh `docs/demo-tuan-1.html` (Midnight Forge, file trên máy, không xuất bản). Chỉ đọc BigQuery và log, không gọi API nguồn, không PII. Gồm: tóm tắt, khớp nguồn (từ `logs/reconcile.json`), cột đơn theo tháng + bảng so báo cáo store, 14 bảng raw, độ mới, sổ quota, chỗ khác brief.
- [x] `reconcile.py` lưu kết quả mới nhất mỗi nguồn ra `logs/reconcile.json`. Tách danh sách bảng sang `checks/raw_spec.py`.
- [x] Kiểm bằng Edge headless: không cuộn ngang, 19 cột, 3 tháng lệch báo cáo store được tô.
- [ ] Chạy `reconcile` để thẻ "Khớp với chính nguồn" có số, rồi sinh lại trang.
- Đính chính: raw có 14 bảng (Shopify 6, Meta 2, Klaviyo 6), không phải 15 như tôi nói trước đó.


## Tuần 2, lát cắt đầu: dbt silver → gold `daily_performance` (kế hoạch 2026-11-10, chờ duyệt)

Mục tiêu: một chỉ số đi hết đường raw → silver → gold, khớp số đã đối chiếu ở raw. Chỉ Shopify + Meta. Klaviyo, line items, `dim_product` để lát sau.

**Ràng buộc Sandbox:** chỉ `view`/`table` (`CREATE OR REPLACE`), không `incremental`. **Không partition** bảng gold: Sandbox xoá partition cũ hơn 60 ngày, nên partition theo ngày sẽ làm mất ngày 2024–2026. `maximum_bytes_billed` đặt trong profile.

### 1. Khung dbt
- [x] `transform/dbt_project.yml`, `transform/profiles.yml` (method `service-account`, đọc `GCP_PROJECT_ID`, `GOOGLE_APPLICATION_CREDENTIALS`, `BQ_LOCATION` qua `env_var`, `maximum_bytes_billed` 1 GB). Profile path tương đối, nên luôn chạy từ `transform/`. (13/11 rà: xong)
- [x] Macro `generate_schema_name`: model vào đúng dataset `silver` / `gold`, không thành `xxx_silver`. (13/11 rà: xong: macros/generate_schema_name.sql)
- [x] `sources.yml` khai `raw.shopify_orders`, `raw.meta_ad_insights_daily` + test khoá duy nhất. (13/11 rà: xong)
- [x] `pipelines/dbt.py`: nạp `.env` bằng dotenv, đổi thư mục sang `transform/`, gọi `dbt.cli.main` (vì `dbt.exe` bị Application Control chặn). Lệnh: `python -m pipelines.dbt build`. (13/11 rà: xong)

### 2. Silver (view)
- [x] `stg_shopify_orders`: `order_date` = ngày của `created_at` theo `America/Phoenix`; `rev` = `current_total`; cờ `is_test`, `is_cancelled`; bỏ cột `_dlt_*`. (13/11 rà: xong)
- [x] `stg_meta_ad_insights`: `date`, `ad_account_id`, `campaign_id`, `ad_id`, `spend`, `impressions`, `clicks`, `inline_link_clicks`, `purchases` (chỉ lấy `purchase` trong `actions`, không cộng `omni_purchase`). (13/11 rà: xong)
- [x] Test: khoá duy nhất, not_null `order_date`/`date`, `spend >= 0`. (13/11 rà: xong)

### 3. Gold (table)
- [x] `daily_performance` theo `date` (Phoenix): `orders`, `rev`, `spend`, `mer` = `rev / spend` (null khi chưa có spend: Meta mới nạp từ 1/8/2026), `cpo` = `spend / orders`, `meta_purchases` để tham khảo. Đơn tính trên đơn không test. Đơn huỷ: tạm giữ trong cả `orders` lẫn `rev`, chốt lại ở bước 4. (13/11 rà: xong)
- [x] Mô tả từng cột (định nghĩa chỉ số) ngay trong `schema.yml`, để sau này MCP đọc định nghĩa từ đó. (13/11 rà: xong: _marts.yml + metrics.yml)

### 4. Kiểm số (Huy Anh chạy, vì dùng khoá GCP)
- [x] `python -m pipelines.dbt build`: mọi test PASS. (13/11 rà: xong)
- [x] `checks/check_gold.py`: tổng 1–7/11 so với số đã khớp ở raw: **815 đơn**, spend **24.098,67**; tổng spend gold = tổng spend raw cả kỳ; tổng đơn gold = số đơn không test trong raw. Nếu 815 chỉ khớp khi bỏ đơn huỷ thì đổi định nghĩa ở bước 3 cho khớp. (13/11 rà: thay bằng câu kiểm trong checks/sql; 815 đơn đã khớp)
- [x] Ghi định nghĩa đang dùng là **tạm**, chờ `context/metrics.md` của anh Quang (cổng khớp số tuần 3). (13/11 rà: xong: metrics.yml status tam)

### Chưa làm trong lát này
CM ước (cần COGS 28% và phí 3,8% theo brief, xác nhận với `context/cogs.csv`), Klaviyo, `fct_order_lines`, `dim_product`, MCP server.

## Khám phá schema Meta trước khi pull hết lịch sử (kế hoạch 2026-11-10, chờ duyệt)

Anh Quang (10/11): Meta nhiều bảng (3–4 bảng phải join mới đọc được), lấy **1 ngày** để hiểu trước, tìm phương pháp khám phá schema rồi mới pull, không là ngộp. Anh bảo gom hết lịch sử.

**Hiện đang có:** `meta_ad_insights_daily` (ad × ngày, 14 trường, đã kèm id/tên campaign, adset) và `meta_ads` (ad → adset, campaign, objective, creative_id). **Chưa có:** bảng campaign (status, budget, buying type), adset (optimization goal, billing event, targeting, budget), creative (title, body, CTA, link, ảnh/video, `object_story_spec`, `asset_feed_spec`), danh sách action_type thật sự xuất hiện.

**Tạm dừng nạp lịch sử tháng 4 trở về trước** cho tới khi chốt trường cần lấy. Lý do: chốt trường xong mới pull 18 tháng một lần, khỏi pull lại cả lịch sử khi thêm trường.

### Phương pháp: 3 lớp, mỗi lớp tốn ít lần gọi hơn lớp sau
1. **Hỏi Meta tự mô tả (`?metadata=1`)**: gọi 1 lần cho mỗi loại node (campaign, adset, ad, adcreative) với một id có thật. Meta trả danh sách mọi trường (tên, kiểu, mô tả) và các connection. Khoảng 4 lần gọi. Nếu v27 không còn hỗ trợ thì dùng trang reference của Marketing API thay thế.
2. **Lấy mẫu 1 ngày thật (7/11, ngày đã đối chiếu)**: chỉ những campaign/adset/ad/creative có spend trong ngày đó (khoảng 35 campaign, 313 ad), xin **mọi trường** ở lớp 1, cùng insights 1 ngày. Lưu JSON thô ở `data/meta_explore/` (đã gitignore, không ghi BigQuery). Khoảng 10–20 lần gọi, đi qua `meta.get` nên vẫn giãn 15 giây và giữ quota.
3. **Profile trên máy (không gọi mạng)**: `checks/profile_meta.py` duỗi JSON lồng nhau thành đường dẫn (`object_story_spec.link_data.call_to_action.type`...), in cho từng bảng: tỉ lệ có giá trị, kiểu, số giá trị khác nhau, ví dụ. Liệt kê mọi `action_type` trong `actions`/`action_values` kèm tổng của ngày 7/11.

### Kiểm quan hệ bảng trên mẫu
- [x] Vẽ sơ đồ: account → campaign → adset → ad → creative; insights (date, ad_id) nối về ad. (13/11 rà: xem docs/meta-schema.md)
- [x] Kiểm khoá nối: mọi `ad_id` của insights có trong ads; mọi `adset_id`, `campaign_id`, `creative_id` của ads có trong bảng tương ứng. Đếm số mồ côi (ad đã xoá). (13/11 rà: xem docs/meta-schema.md)
- [x] Kiểm grain: 1 creative dùng cho nhiều ad? 1 ad đổi creative theo thời gian? (13/11 rà: xem docs/meta-schema.md)
- [x] Spend cộng theo ad = theo adset = theo campaign của ngày 7/11. (13/11 rà: xem docs/meta-schema.md)

### Đầu ra
- [x] `docs/meta-schema.md`: từng bảng có grain, khoá, khoá nối, trường quan trọng, trường bỏ (kèm lý do), bẫy (action_type trùng nghĩa, attribution window, `reach` không cộng được). (13/11 rà: xong: docs/meta-schema.md)
- [x] Đề xuất danh sách trường + bảng raw mới (`meta_campaigns`, `meta_adsets`, `meta_creatives`), mang cho anh Quang duyệt. (13/11 rà: xong)
- [x] Duyệt xong mới sửa `pipelines/sources/meta.py` rồi pull lịch sử về 11/2024 (hoặc mốc anh chốt). (13/11 rà: xong, mốc lịch sử chốt 1/2026)

### Nguyên tắc
- Chỉ đọc. Huy Anh chạy lớp 1–2 (dùng token), mình viết script + test bằng phản hồi giả trước.
- Chạy ngoài giờ làm việc Phoenix, mỗi lần chạy in số lần gọi và mức dùng.

## Chiều 2026-11-10: phương pháp khám phá dữ liệu cho cả 3 nguồn → 1 buổi present (kế hoạch, chờ duyệt)

Mục tiêu buổi present: với Shopify, Meta, Klaviyo, trả lời được 4 câu: **có những bảng gì** (cấu trúc), **mỗi dòng là gì** (grain + khoá), **nối với nhau thế nào** (quan hệ), **số đó nghĩa là gì trong kinh doanh D2C** (ý nghĩa + bẫy). Meta làm kỹ nhất vì nhiều bảng nhất.

### Một phương pháp chung, 4 bước, áp cho từng nguồn
| Bước | Câu hỏi | Shopify | Meta | Klaviyo |
|---|---|---|---|---|
| 1. Hỏi nguồn tự mô tả | Có trường gì, kiểu gì | GraphQL introspection `__type(name: "Order")` | `?metadata=1` trên campaign/adset/ad/creative | OpenAPI spec công khai của Klaviyo (không cần token) |
| 2. Mẫu 1 ngày (7/11) | Dữ liệu thật trông thế nào | Đơn ngày 7/11 + line items, refunds, product | Đối tượng có spend 7/11, đủ trường | Campaign/flow/metric + đếm ngày 7/11 |
| 3. Profile trên máy | Trường nào có giá trị, lồng ra sao | chung một script `checks/profile_sample.py`: duỗi JSON lồng nhau, tỉ lệ có giá trị, kiểu, số giá trị khác nhau, ví dụ | | |
| 4. Kiểm quan hệ + ý nghĩa | Nối được không, số có khớp không | đơn ↔ line item ↔ variant ↔ product | ad ↔ adset ↔ campaign, ad ↔ creative, spend 3 cấp bằng nhau | message ↔ campaign/flow, Placed Order ↔ đơn Shopify |

### Việc chiều nay
- [x] (10/11) `checks/explore_meta.py`, `explore_shopify.py`, `explore_klaviyo.py`: metadata/introspection + mẫu ngày 7/11, tự bỏ trường bị từ chối (ghi `_dropped.json`). Shopify tự dựng query từ introspection, bỏ trường PII. Klaviyo không cần OpenAPI spec vì JSON:API trả đủ attributes. Thêm `MetaError` (vẫn là SystemExit) và `shopify.graphql_body` để đọc lỗi theo trường.
- [x] `checks/profile_sample.py` (bước 3). `tests/test_explore.py` PASS, cả 9 bộ test PASS.
- [x] Huy Anh chạy 10/11 ~12:00: Klaviyo 29 lần gọi 0%, Shopify 21 lần 1,9%, Meta 42 lần 18%, 0 trường bị từ chối. Kiểm quan hệ Meta: khoá nối 100%, spend 3 lần gọi độc lập lệch ≤ 0,17 USD. Phát hiện: `?metadata=1` rỗng ở v27; edge adcreatives không lọc id IN (mới lấy 20/215 creative); bộ trường rộng trả cả ad không chạy (2.654 dòng, 210 có impression); 1 lượt mua mang 8 tên action_type; Meta nhận 116/128 đơn, Klaviyo 2/128; tiền tố SKU thật có ULS, TPC, AUH, APC ngoài brief.
- [x] `docs/meta-schema.md`. (Chưa cập nhật `docs/raw-tables.md` cho Shopify, Klaviyo: chờ anh chốt trường.)
- [x] Làm trang present HTML `docs/present-3-nguon.html` bằng `python checks/present_page.py`; kiểm Edge headless 1280px và browser pane 375px không tràn ngang (chốt 10/11; Midnight Forge, sinh từ mẫu như `checks/demo_page.py`, mở trên máy, không xuất bản): sơ đồ quan hệ bảng mỗi nguồn, mỗi nguồn 1 trang "4 câu hỏi", đề xuất trường cần thêm cho raw, câu hỏi cần anh chốt.

### Sau buổi present
Anh chốt trường → sửa pipeline → gom hết lịch sử Meta, Klaviyo về 11/2024 (hoặc mốc anh chốt).

- [ ] Lần sau lấy creative lồng trong ad (`ads?fields=creative{...}`) để đủ 215 creative với ~5 lần gọi.
- [ ] Khám phá `customerJourneySummary` của Shopify (UTM) để nối đơn → ad.
- [x] (10/11) Viết `docs/kham-pha-nguon-moi.md`: checklist 6 phần (chuẩn bị, 4 bước, chốt) dùng cho mọi vùng dữ liệu mới, kèm lỗi hay gặp lấy từ Shopify, Meta, Klaviyo.

## Giảm lần gọi Meta (10/11, sau khi gặp mã 4)
- [x] Hôm nay gọi Meta 154 lần (reconcile so lại cả kho sau mỗi tháng: 13–17 lần mỗi lượt), lúc ~15:00 giờ VN gặp mã 4 (giới hạn cả app, chung với đội ads).
- [x] `reconcile.py`: mặc định chỉ so 7 ngày đã trọn; `--since/--until` so đúng khoảng vừa nạp (Meta 1 tháng = 2 lần gọi); `--all` mới so cả kho.
- [x] `meta.get`: mã 4 thì dừng hẳn, ghi sổ, không thử lại (trước đây chờ 300 giây × 5 lần). Mã 17/32/613/80000/80004 vẫn chờ 300 giây.
- [x] Test: thêm ca mã 4 (test_limits) và ca khoảng so (test_reconcile). 9 bộ test PASS.
- [x] Báo anh Quang việc chạm mã 4 lúc ~15:00 giờ VN 10/11. (13/11 rà: đã ghi trong PROGRESS 10/11)
- [x] Gặp mã giới hạn của Meta (4, 17, 32, 613, 80000, 80004) thì ghi sự kiện kèm nguyên header mức dùng vào `logs/limits.jsonl` (`Tracker.event`, có `"event": true`). Trang demo bỏ qua các dòng sự kiện. 9 bộ test PASS.

## Dừng mọi lệnh gọi API (anh Quang, 10/11 chiều)
- [x] Anh Quang: "giờ thì đừng làm gì, anh đang làm". Agent của anh gọi thẳng Meta API, chưa tối ưu, nên tốn nhiều quota (phần lớn mã 4 lúc 15:00 có thể từ đây). Không chạy `pipelines.run`, `reconcile`, `explore_*` cho tới khi anh báo xong. (13/11 rà: hết hiệu lực: anh đã cho chạy lại từ 11/11)
- [x] Hệ quả đã biết: Meta, Klaviyo sẽ quá 36 giờ từ khoảng 02:00 giờ VN 11/11, `check_raw` báo ✗. Không phải lỗi dữ liệu; anh báo xong thì chạy `python -m pipelines.run` để nạp từ 9/11. (13/11 rà: hết hiệu lực: kho mới trong 36 giờ từ 11/11)

## dbt lát cắt đầu: làm từng bước (Huy Anh duyệt 10/11 chiều)
- [x] Bước 1 (khung): `transform/dbt_project.yml` (staging → silver view, marts → gold table), `profiles.yml` (service-account, đọc env, `maximum_bytes_billed` 1 GB), macro `generate_schema_name` (ghi đúng dataset silver/gold), `models/staging/_sources.yml` (raw.shopify_orders, raw.meta_ad_insights_daily + 6 test khoá/not_null), `pipelines/dbt.py` (gọi dbt qua Python, tự trỏ transform/, đổi khoá sang đường dẫn tuyệt đối). `dbt parse` với khoá giả OK: 2 source, 6 test.
- [x] Huy Anh chạy `python -m pipelines.dbt debug` (OK) rồi `python -m pipelines.dbt test` (6/6 PASS) ngày 10/11.
- [x] Bước 2 (code): `stg_shopify_orders` (order_date theo Phoenix, rev = current_total, cờ is_test/is_cancelled), `stg_meta_ad_insights` (spend, meta_purchases chỉ lấy action_type 'purchase'), `_staging.yml` 7 test. dbt parse OK (13 test, 2 model).
- [x] Huy Anh build silver (10/11): 1–7/11 không test = **815 đơn**, rev 44.370,74, khớp số tuần 1. Kết luận: 815 là đếm cả đơn huỷ.
- [x] Bước 3 (code): `marts/daily_performance.sql` (orders, cancelled_orders, rev, spend, mer, cpo, meta_purchases, meta_roas; spend null trước ngày Meta đầu tiên), `_marts.yml` 4 test. dbt parse OK (17 test, 3 model).
- [x] Huy Anh chạy `python -m pipelines.dbt build` (10/11): PASS=20 (3 model + 17 test), ERROR=0. Kiểm 1–7/11 trên gold: 815 đơn, rev 44.370,74, spend 24.098,56, MER 1,8412.
- [x] Bước 4: số gold khớp số đã đối chiếu tuần 1 (815 đơn; spend lệch 0,11 so với 24.098,67 lúc nạp đầu, do Meta chỉnh số ngày gần).

### Review lát cắt dbt đầu (10/11)
- Đường raw → silver (view) → gold (table) chạy bằng 1 lệnh `python -m pipelines.dbt build`, không gọi API nguồn, mỗi truy vấn chặn 1 GB.
- Định nghĩa đang dùng (tạm, chờ `context/metrics.md`): orders = đơn không test kể cả huỷ; rev = current_total; spend = Meta mọi tài khoản; MER = rev/spend; CPO = spend/orders. Spend null trước 1/3/2026.
- Chưa có: CM ước (cần COGS/phí), Klaviyo, line items, dim_product, MCP đọc gold.
- [x] Bước 2: silver. Bước 3: gold. Bước 4: kiểm số 1–7/11. (13/11 rà: xong)

## MCP server đọc gold (10/11 chiều)
- [x] `mcp_server/server.py` (mcp 2.3, MCPServer): 4 tool chỉ đọc `gold.daily_performance`: `performance_summary` (tổng khoảng ngày, MER/CPO tính từ tổng, ghi chú ngày thiếu / thiếu Meta), `daily_performance` (theo ngày), `metric_definitions` (đọc từ `_marts.yml`), `today_phoenix`. SQL viết sẵn, ngày truyền bằng query parameter, `maximum_bytes_billed` 200 MB, lỗi raise ToolError.
- [x] `.mcp.json` để Claude Code nạp server `datae`. `tests/test_mcp_server.py` PASS; mở server thật qua stdio liệt kê đủ 4 tool. 10 bộ test PASS.
- [x] Huy Anh mở phiên Claude Code mới trong DataE, duyệt server `datae`, hỏi thử: tổng 1–7/11 phải ra 815 đơn, MER 1,84. (13/11 rà: xong)
- [x] Khác brief: đang dùng service account của pipeline (Data Editor). Brief muốn MCP dùng service account chỉ đọc silver + gold. Cần Huy Anh tạo SA mới trên console (BigQuery Data Viewer trên gold/silver + Job User). (13/11: XONG, khoá datae-mcp chỉ đọc gold, check_mcp_key 5/5)

## Silver + gold vòng 2 (kế hoạch 2026-11-10, chờ duyệt)

Dashboard + Claude sửa dashboard: để sau (Huy Anh chốt concept: dashboard đọc gold, Claude Code sửa `dashboard/spec.yml`). Giờ chỉ làm silver, gold. Mỗi bước: viết model + test → `dbt parse` với khoá giả → Huy Anh `dbt build --select <model>` → 1 câu SQL kiểm số với số đã biết. Không gọi API nguồn.

### Bước A: Shopify theo sản phẩm (brief: `dim_product` quan trọng nhất)
- [x] (10/11, code) Silver `stg_shopify_line_items`, `stg_shopify_products`, `stg_shopify_variants`; seed `product_lines.csv` (4 tiền tố của brief); gold `dim_product`, `product_daily`. dbt parse OK: 8 model, 1 seed, 40 test. Câu kiểm: `checks/sql/check_buoc_a.sql`.
- [x] Huy Anh build + 3 câu kiểm (10/11): units 1.338 = 1.338 ✓; **line_revenue 44.622,96 > rev 44.370,74 ✗**. Nguyên nhân (mẫu 7/11): `discountedTotal` chưa trừ mã giảm giá cả giỏ (343,79) và hàng trả. SKU số (100, 120...) toàn T-Shirt → tiền tố chỉ có nghĩa với SKU chữ, productType là nguồn chính. Có UpCart Shipping Protection, Gift Card, 9 đơn '(không rõ)' lẫn vào doanh thu sản phẩm → hỏi anh Quang.
- [x] Sửa tận gốc: pipeline Shopify lấy thêm `discountedUnitPriceAfterAllDiscountsSet` → `unit_price_after_discounts`, `priceAfterAllDiscountsBeforeTaxesSet` → `line_net`; silver `line_revenue` = `line_net`. test_shopify PASS, dbt parse OK (41 test), 10 bộ test PASS.
- [x] Huy Anh chạy `load_shopify --full` (code mới) + `dbt build` (10/11): 1–7/11 line_revenue **41.214,26** < rev 44.319,85 ✓; so current_subtotal 41.159,83 lệch +54,43 (0,13%) ✓. Rev giảm 44.370,74 → 44.319,85 do hoàn tiền mới: số ngày cũ còn đổi theo thời gian (hỏi anh Quang morning.html chốt Rev lúc nào).
- [ ] Tìm 54,43 còn lệch: nghi là các dòng '(không rõ)' (không productType, không SKU) mà subtotal không tính.
- [x] (chi tiết gốc) `stg_shopify_line_items`: line_item_id, order_id, sku, product_id, variant_id, product_type, quantity, current_quantity, unit_price, line_revenue (`discounted_total`), `sku_prefix` (3 chữ đầu).
- [x] `stg_shopify_products`, `stg_shopify_variants`.
- [x] Seed `seeds/product_lines.csv`: tiền tố SKU → dòng sản phẩm. Đã biết từ brief: MHL Sun Hoodie, SSS Button-up, AUX Short Sleeve tee, RGO Ornament. Chưa biết (ghi "chưa chốt"): ULS, TPC, AUH, APC → hỏi anh Quang. (13/11 rà: seed có đủ; nghĩa tiền tố suy từ tên vẫn chờ anh duyệt, xem dòng CHỜ bên dưới)
- [x] Gold `dim_product`: product_id, title, product_type, product_line (productType trước, tiền tố SKU kiểm chéo), status.
- [x] Gold `product_daily`: ngày Phoenix × product_line: đơn, số lượng, doanh thu dòng.
- Kiểm: tổng line_revenue theo đơn ≈ subtotal của đơn; 1–7/11 tổng số lượng khớp `sum(quantity)` raw. Lưu ý: doanh thu dòng chưa gồm ship, thuế, nên nhỏ hơn rev của `daily_performance`; ghi rõ trong mô tả cột.

### Bước B: Hoàn tiền
- [x] `stg_shopify_refunds`: refund_id, order_id, refund_date (Phoenix), total_refunded.
- [x] Gold thêm vào `daily_performance`: `refunds` theo ngày hoàn (khác ngày đặt).
- Kiểm: tổng refunds = tổng `total_refunded` của orders.

### Bước C: Meta theo campaign, ad, phễu
- [x] `stg_meta_ad_insights` thêm phễu: view_content, add_to_cart, initiate_checkout (mỗi bước chỉ 1 tên action_type, như purchase).
- [x] `stg_meta_ads`: ad_id, created_time, effective_status (ghi rõ: trạng thái hôm nay), creative_id.
- [x] Gold `campaign_daily`: ngày × campaign: spend, impressions, clicks, link_clicks, phễu, meta_purchases, CTR, CPM (tính từ tổng). (13/11 rà: thay bằng fct_ad_day ngày × ad có campaign_name, adset_name + tool ad_performance gom theo campaign)
- [x] Gold `ad_daily`: ngày × ad: như trên + tuổi ad (ngày − created_time), `LEFT JOIN` cây ad (51 dòng ad đã xoá không bị rơi). (13/11 rà: thay bằng fct_ad_day, có ad_age_days)
- Kiểm: tổng spend `campaign_daily` = tổng spend `daily_performance` mọi ngày.

### Bước D: Klaviyo
- [x] `stg_klaviyo_message_daily`: ngày × message × metric, bỏ message `(none)` khi tính doanh thu email.
- [x] `stg_klaviyo_messages`: gộp campaign message + flow message → message_id, kênh (campaign/flow), tên.
- [x] Gold `email_daily`: ngày × kênh × tên: received, opened, clicked, placed_order, value; open rate, click rate từ tổng.
- [x] `daily_performance` thêm `email_orders`, `email_value` (Klaviyo tự nhận, chỉ tham khảo).
- Kiểm: tổng placed_order (kể cả `(none)`) theo ngày = số reconcile Klaviyo đã khớp.

### Chưa làm trong vòng này
CM ước (cần COGS 28% + phí 3,8% xác nhận với `context/cogs.csv`), MCP tool cho bảng gold mới (làm sau khi gold ổn), dashboard.

## Kế hoạch vòng 2 sửa theo brief tuần 2 (10/11, Huy Anh duyệt từng bước)
1. [x] Đổi tên model silver theo brief: `stg_orders`, `stg_line_items`, `stg_products`, `stg_variants`, `stg_meta_ad_day`. Sửa ref trong `daily_performance`, `dim_product`, `product_daily`, `_staging.yml`, `checks/sql/check_buoc_a.sql`. dbt parse OK (8 model, 41 test).
   - [x] Huy Anh build + xoá 5 view tên cũ (`checks/drop_old_views.py`).
2. [x] (code) `stg_refunds` (refund_date theo Phoenix, refund_amount) + test unique, relationships → stg_orders. Câu kiểm `checks/sql/check_buoc_b.sql`.
   - [x] Huy Anh build + kiểm (10/11): 116 lần hoàn, 87 đơn; tổng hoàn theo lần 4.382,56 = tổng total_refunded trên đơn 4.382,56; câu 2 (đơn lệch) rỗng ✓. Hoàn theo tháng: cao nhất 9/2026 (26 lần, 1.152,42).
3. [ ] `intermediate/` + `fct_orders`, `fct_lines` (nối `dim_product`), `fct_ad_day`, test `relationships` sang dim.
4. [ ] `dim_customer` (đơn đầu, số đơn, LTV theo `customer_key`).
5. [ ] `dim_product` thêm species, theme từ tag (xem quy ước tag trước).
6. [ ] Freshness cho raw trong `_sources.yml`.
7. [ ] `daily_performance`, `product_daily` dựng lại từ fact; số giữ nguyên (815 đơn 1–7/11, line_revenue 41.214,26).
8. [ ] `stg_klaviyo_message_daily` (brief ghi `stg_klaviyo_events`; mình không lấy event thô vì có email).

### Vòng 2 làm hết một lượt (10/11 tối, Huy Anh: "lọc với tổng hợp hết cho xong")
- [x] Silver thêm: `stg_meta_ads`, `stg_klaviyo_message_daily` (thay stg_klaviyo_events), `stg_klaviyo_messages` (campaign + flow); `stg_meta_ad_day` thêm phễu (view_content, add_to_cart, initiate_checkout) qua macro `meta_action`.
- [x] Intermediate: `int_order_refunds`.
- [x] Fact: `fct_orders` (is_first_order, refund_count, units), `fct_lines` (product_line chọn 1 lần), `fct_ad_day` (creative, objective, tuổi ad, in_ad_tree).
- [x] Dim: `dim_customer` (cohort, số đơn, LTV, khách quay lại), `dim_product` thêm species, species_all, theme (pc1/orn1/ls1), artist, gender, water từ tag.
- [x] Bảng tổng dựng lại từ fact: `daily_performance` (+ first_orders, refunds theo ngày hoàn, email_orders, email_value), `product_daily`, mới `email_daily`.
- [x] Test: relationships fact → dim (fct_orders → dim_customer; fct_lines → fct_orders, dim_product cảnh báo; fct_ad_day → stg_meta_ads cảnh báo), accepted_values, freshness cho raw (36 giờ cảnh báo, 72 giờ lỗi). dbt parse OK: 18 model, 1 seed, 90 test. MCP test PASS.
- [x] Huy Anh `dbt build` (10/11): PASS=108, WARN=1 (đúng 51 dòng ad đã xoá, đã dự kiến), ERROR=0. Chạy `check_vong2.sql`, Huy Anh xác nhận số hợp lý (mình chưa xem số cụ thể của câu 3, 5, 6, 7).

### Review vòng 2 (10/11)
- Đủ checklist tuần 2 của brief: staging/intermediate/marts; silver 9 view; gold dim_product (có species, theme từ tag), dim_customer, fct_orders, fct_lines, fct_ad_day; test unique/not_null, relationships fact → dim, freshness raw.
- Khác brief: stg_klaviyo_events → stg_klaviyo_message_daily (không lấy event thô vì có email); thêm stg_variants, stg_meta_ads, stg_klaviyo_messages và 3 bảng tổng cho MCP.
- Chờ anh Quang: ánh xạ tiền tố SKU chữ, có tính UpCart/Gift Card/(không rõ) vào doanh thu sản phẩm không, morning.html chốt Rev lúc nào, `context/metrics.md`, COGS cho CM.
- Tiếp: MCP thêm tool cho bảng gold mới; CM ước; dashboard (spec.yml).
- [x] `python -m pipelines.dbt source freshness` (11/11 10:24 giờ VN): 3/3 PASS. Shopify 8,1 giờ; Meta, Klaviyo có tới hết 9/11 Phoenix (27,4 giờ, dưới ngưỡng cảnh báo 36 giờ).

## Thử MCP datae trong phiên (10/11)
- [x] Gọi 4 tool: today_phoenix (10/11, ngày trọn 9/11) ✓; performance_summary 1–7/11 = 815 đơn, rev 44.319,85, spend 24.098,56, MER 1,8391 ✓ khớp câu kiểm.
- [x] Lỗi tìm ra: (1) 9/11, 10/11 chưa nạp Meta mà spend = 0, cpo = 0 (chỉ xử lý đầu khoảng Meta, quên cuối); (2) ngày không có đơn không có dòng, MCP báo 'kho chỉ có 4/7 ngày' như thiếu dữ liệu. Sửa `daily_performance`: lịch đủ mọi ngày (generate_date_array), spend null ngoài [ngày Meta đầu, ngày Meta cuối]. Sửa ghi chú MCP. dbt parse OK, test MCP PASS.
- [x] Huy Anh build (PASS=108, WARN=1 như cũ). Gọi lại MCP: 9/11, 10/11 spend/mer/cpo = null ✓; 25/2–3/3 đủ 7 ngày, ngày không đơn orders = 0 ✓; 1–7/11 vẫn 815 đơn, rev 44.319,85, spend 24.098,56 ✓. Ghi chú chữ của MCP còn bản cũ tới khi mở phiên mới.
- Quan sát: 25/2–3/3 shop chỉ 0–4 đơn/ngày (so với 100+ đơn/ngày tháng 11). Hỏi anh Quang: gom Meta về 11/2024 có đáng không.

## Review ngày 10/11 (tối)

Tầng raw gần đủ lịch sử, silver + gold đủ checklist tuần 2, MCP đọc được gold. Đã chứng minh bằng số:
- **Raw:** Meta, Klaviyo có 1/3–8/11/2026, mỗi tháng reconcile khớp nguồn (Meta mọi ngày lệch < 1 USD, Klaviyo khớp tuyệt đối). Shopify nạp lại `--full` với 2 trường giá dòng mới.
- **dbt (silver 9 view + 1 intermediate, gold 8 bảng):** PASS=108, WARN=1 (51 dòng ad đã xoá, đã biết). 1–7/11: 815 đơn, rev 44.319,85, spend 24.098,56, MER 1,84; doanh thu dòng 41.214,26 khớp current_subtotal (lệch 0,13%); hoàn tiền 4.382,56 = total_refunded.
- **MCP `datae`:** 4 tool đọc gold, gọi thật trong phiên ra đúng số. Thử thật tìm ra 2 lỗi gold (spend 0 ngày chưa nạp, thiếu ngày không đơn), đã sửa và kiểm lại.
- **Khám phá schema 3 nguồn** (phương pháp 4 bước, `docs/kham-pha-nguon-moi.md`, `docs/meta-schema.md`, `docs/present-3-nguon.html`).
- **Giảm quota Meta:** gọi insights theo đoạn ≤ 7 ngày; mã 1/2 thử lại; mã 4 dừng hẳn; reconcile chỉ so khoảng vừa nạp (1 tháng = 2 lần gọi thay vì 13–17); ghi header khi bị chặn.
- **Lỗi tìm ra trong ngày:** Meta quá tải khi hỏi cả tháng; reconcile so lại cả kho làm chạm mã 4 (phần lớn do agent anh Quang); doanh thu dòng dùng sai trường (`discountedTotal` chưa trừ giảm giá cả giỏ); `dbt_project.yml` vấp chữ có dấu; gold spend 0 thay vì null.
- 11 bộ test PASS.
Còn: gom Meta/Klaviyo tháng 2, 1/2026 (dừng tới khi anh Quang báo); nạp ngày 9/11 trở đi; MCP tool cho bảng gold mới; CM ước; service account chỉ đọc cho MCP.

## Ngày mai 2026-11-11

Nạp (chỉ khi anh Quang báo đã xong việc, theo khung giờ anh chốt):
- [x] `python -m pipelines.run` (7 ngày gần nhất, gồm 9/11, 10/11) → `python checks/reconcile.py` → `python -m pipelines.dbt build`. (13/11 rà: xong 11/11)
- [x] Tháng 2/2026, rồi tháng 1/2026 (cách ≥ 1 giờ), mỗi tháng reconcile đúng khoảng đó. (13/11 rà: lịch sử Meta, Klaviyo đã về 1/1/2026, mọi tháng khớp nguồn)

Làm (không đụng quota Meta):
- [x] MCP thêm tool: `product_performance` (product_daily), `ad_performance` (fct_ad_day), `email_performance` (email_daily), `customer_summary` (dim_customer). Test bằng BigQuery giả, rồi thử thật trong phiên mới. (13/11 rà: xong, nay 15 tool)
- [x] Hướng dẫn tạo service account chỉ đọc silver + gold cho MCP (brief). (13/11 rà: CHƯA LÀM. MCP đang dùng khoá datae-pipeline có quyền ghi; brief cần khoá chỉ đọc silver + gold) (13/11: XONG, khoá datae-mcp chỉ đọc gold, check_mcp_key 5/5)

Demo tuần 2 với anh Quang (15 phút):
- [x] Mở phiên Claude có MCP `datae`, hỏi trực tiếp: "MER tuần trước", "dòng sản phẩm nào bán chạy", "khách quay lại bao nhiêu %". (13/11 rà: đã hỏi thật nhiều lần)
- [x] Chạy `python -m pipelines.dbt build` (PASS=108) và 1 câu trong `checks/sql/check_vong2.sql`. (13/11 rà: các lần build sau PASS=152)
- [x] Nói rõ chỗ khác brief: stg_klaviyo_events → số đếm ngày × message (không PII); không partition (Sandbox); định nghĩa chỉ số đang tạm. (13/11: README mục 6 gom đủ 9 dòng khác brief)

Hỏi anh Quang (chặn tuần 3):
- [ ] Khung chạy Meta 00:00–06:00 là giờ Việt Nam hay Phoenix?
- [ ] Ánh xạ tiền tố SKU chữ ULS, TPC, AUH, APC; có tính UpCart Shipping Protection, Gift Card, dòng "(không rõ)" vào doanh thu sản phẩm không?
- [ ] `context/metrics.md`, `context/cogs.csv`, `dashboard/morning.html`: lấy ở đâu? morning.html chốt Rev lúc nào (Rev ngày cũ giảm dần khi có hoàn)? (13/11 rà: morning.html anh đã chốt bỏ 12/11; còn metrics.md, cogs.csv)
- [ ] Tháng 3/2026 có 4 tài khoản ads cùng chạy, từ tháng 4 dồn về 918678220936371: vì sao? Tháng 1–2 chạy tài khoản nào?
- [ ] Billing (rời Sandbox: bảng tự xoá sau 60 ngày), repo, chỗ chạy lịch tự động.
- [ ] (cũ) 11 đơn PAID báo cáo store; quyền xem Shopify Admin.

Tự học từ code tuần 2 (để trả lời được khi demo):
- [ ] `transform/models/marts/daily_performance.sql`: vì sao có lịch đủ ngày và spend null ngoài khoảng Meta.
- [ ] `fct_orders.sql`: `is_first_order` tính bằng `row_number()` thế nào.
- [ ] `dim_product.sql`: đọc species, theme từ tag `species:`, `pc1:`.
- [ ] `mcp_server/server.py`: vì sao MER tính từ tổng, không lấy trung bình.

Cuối ngày:
- [x] Ghi 3 dòng vào `PROGRESS.md`.

## 11/11
- [x] Tháng 2/2026 (08:03 giờ VN): Meta 5 lần gọi, 2%, chỉ 1 tài khoản có spend, 312 dòng (6/43/189/74 theo tuần: shop bắt đầu chạy ads mạnh từ giữa tháng 2); ad_insights_daily 19.394. Klaviyo chỉ 8 dòng, dữ liệu bắt đầu 14/2. check_raw: bảng đủ, khoá trùng 0; chỉ báo Meta, Klaviyo trễ 42 giờ (dự kiến: chưa nạp 9/11 trở đi).
- [x] Reconcile tháng 2 (2 lần gọi Meta, 2%): Meta ✓ spend 1.016,71 = 1.016,71, 17 ngày có spend; Klaviyo ✓ Placed Order 15 = 15, 8 ngày.
- [x] Shopify incremental + dbt build (11/11 sáng): gold 9/11 = 121 đơn, rev 6.526,77; 10/11 = 104 đơn, rev 5.071,39 (ngày Phoenix chưa trọn). Kiểm qua MCP: spend 9–10/11 null đúng; ghi chú MCP đã là bản mới.
- [x] (chạy 11/11 10:29, xem dưới) Từ 09:05 (Meta, Klaviyo): `python -m pipelines.run` (7 ngày gần nhất) để hết trễ. Tháng 1 từ ~10:05. Rồi `dbt build`.
- [x] Lỗi `python -m pipelines.dbt docs generate` im lặng: `pipelines/dbt.py` chèn `--project-dir` sau chữ đầu, lệnh 2 chữ (docs generate, source freshness) bị dbt từ chối mà không in lỗi. Sửa: thêm vào cuối lệnh, in lỗi khi thất bại. Kiểm bằng khoá giả: cách cũ 'No such option', cách mới qua được tới bước kết nối.
- [x] `dbt docs generate` chạy được (11/11 08:20): 18 model, 90 test, catalog.json ghi xong. Cảnh báo agate "table_owner" là cảnh báo vô hại của dbt-bigquery.
- [x] (11/11) dim_product thêm `product_url` (var store_url = https://thedeerly.com + /products/handle) và `is_live` (ACTIVE); fct_lines thêm `product_title` (tên hiện tại, sản phẩm đã xoá thì tên lúc đặt), `title_at_order`, `product_url`. dbt parse OK.
- [x] (CHỜ, Huy Anh: "để yên đã") Nghĩa tiền tố SKU suy từ tên sản phẩm (11/11, `dim_product` + tên + link): ULS Performance Long Sleeve, MHL AirLite Sun Hoodie, FLS Women's Long Sleeve, SSS Short Sleeve Shirt (button-up), AUX Pro Short Sleeve tee, UST T-Shirt, RGO Glass Ornament, RCO Ceramic Ornament, TPC Tough Phone Case, APC AirPods Case, AUH (Youth) Performance Hoodie, FTB Fleece Throw, QBS Quilt Set, FKC Cardigan, CCL Can Cooler, YTC Trucker Cap, MCT hàng cá nhân hoá nhiều loại; lẻ: ECU, HTT, DTT, EBU, EBT, AUT, CDP, LNW. Phát hiện: productType gộp nhiều dòng con (Long Sleeve = ULS + MHL + FLS; Short Sleeve = SSS + AUX + UST; Ornament = RGO + RCO), nên Sun Hoodie đang tính vào Long Sleeve. Đề xuất (chưa làm): thêm `product_subline` từ tiền tố, giữ `product_line` = productType. (13/11 rà: ĐÃ LÀM 11/11, product_subline từ tiền tố; nghĩa tiền tố vẫn chờ anh duyệt)
- [x] (CHỜ) Huy Anh 11/11: biến thể có phân loại riêng: AUH (hoodie) có loại thường và loại dày; TPC (ốp điện thoại) có MagSafe và standard. Chưa biết nằm ở phần đuôi SKU hay tên biến thể: kiểm bằng câu SQL stg_variants × dim_product (sku, variant title). Nếu dùng thì thêm cột `variant_type` ở stg_variants/fct_lines để so doanh thu MagSafe vs standard, dày vs thường. (13/11 rà: ĐÃ LÀM 11/11, dim_variant + variant_type)
  - Kết quả 11/11 (AUH): loại nằm ở lựa chọn thứ 2 của tên biến thể, có 3 loại: Standard AirKnit (thường), Standard Fleece Lining, Heavyweight Fleece Lining (dày). SKU có ít nhất 4 định dạng khác nhau (AUH-MFKH-518K-S, AUH713K-S, AUH001K không size, AUH-TFH231K-S) nên KHÔNG tách loại từ SKU; MFKH đi với AirKnit, TFH đi với Heavyweight Fleece. Chữ sau số mẫu có K, V, C, R (chưa rõ nghĩa). Còn xem TPC (MagSafe/standard).
  - Kết quả 11/11 (TPC): SKU thống nhất `TPC<số mẫu><chữ>-<STANDARD|MAGSAFE>-<đời máy>`, ví dụ TPC239V-MAGSAFE-IPHONE16. Mỗi kết hợp có 749 biến thể (= 749 mẫu ốp). MagSafe chỉ có cho iPhone; Samsung chỉ Standard. Tên biến thể TPC: lựa chọn 2 là ĐỜI MÁY (ngược với AUH, nơi lựa chọn 2 là loại vải) → không lấy loại theo vị trí cố định. Đề xuất khi làm: `variant_type` = dò từ khoá trong tên biến thể và SKU (magsafe, heavyweight fleece, standard fleece, airknit, standard); thêm `device_model` cho TPC từ phần 3 của SKU.

## Kế hoạch: tách loại biến thể (dim_variant) bằng selectedOptions (11/11, chờ duyệt)

Đã kiểm (`api_menu.py SelectedOption`): mỗi biến thể có danh sách `selectedOptions { name value }`, có TÊN lựa chọn (Size, Material...), nên không phải dò chữ trong tên biến thể hay tách SKU (4 kiểu viết).

1. [ ] Pipeline: `PRODUCTS_QUERY` → variants lấy thêm `selectedOptions { name value }`; raw `shopify_product_variants` thêm cột `selected_options` (JSON). Products/variants vốn lấy full mỗi lần, nên chỉ cần `python -m pipelines.load_shopify` thường, không `--full`.
2. [ ] `tests/test_shopify.py`: phản hồi giả có selectedOptions, kiểm cột JSON.
3. [ ] Huy Anh nạp Shopify, rồi 1 câu SQL liệt kê tên lựa chọn × giá trị theo tiền tố (AUH, TPC, ULS...) để biết shop đặt tên thế nào.
4. [ ] Seed `seeds/variant_types.csv`: giá trị gốc → `variant_type` chuẩn (AirKnit, Fleece, Heavyweight, MagSafe, Standard) + `is_heavyweight`.
5. [ ] Silver `stg_variants`: tách `size`, `material_or_type`, `device_model` theo TÊN lựa chọn; giữ giá trị gốc.
6. [ ] Gold `dim_variant` (1 biến thể): variant_type (chuẩn hoá, chưa có trong seed thì "(chưa ánh xạ)"), size, device_model, device_brand (iPhone/Samsung); `fct_lines` thêm `variant_id` nối `dim_variant` + test relationships; test cảnh báo khi có "(chưa ánh xạ)".
7. [ ] Kiểm: 1–7/11 tổng số lượng, doanh thu theo variant_type = tổng fct_lines (không đổi số); % MagSafe trong ốp iPhone.
- [x] (11/11) Bước 1–2 dim_variant: PRODUCTS_QUERY lấy `selectedOptions { name value }`, raw variants thêm cột JSON `selected_options`; test_shopify PASS (cột JSON, danh sách rỗng không lỗi). Câu xem tên lựa chọn: `checks/sql/check_variant_options.sql`.
- [x] (11/11) Tên lựa chọn thật: Size, Interior Weight (AUH: Standard AirKnit / Standard Fleece Lining / Heavyweight Fleece Lining), Case Type (TPC: Standard / MagSafe), Model (TPC 60 đời máy, APC 7 đời AirPods), Title/Default Title (ornament).
- [x] Bước 4–6: seed `variant_types.csv` (5 dòng); `stg_variants` tách size, type_option_name/value, device_model theo TÊN lựa chọn; gold `dim_variant` (variant_type chuẩn hoá, '(chưa ánh xạ)' nếu thiếu seed, is_heavyweight, device_brand); `fct_lines` thêm size, variant_type, is_heavyweight, device_model, device_brand; test relationships variant_id + accepted_values (cảnh báo). dbt parse OK. Câu kiểm: `checks/sql/check_variant.sql`.
- [x] Huy Anh `dbt build` (11/11 09:26): PASS=115, WARN=1 (51 dòng ad đã xoá, như cũ), ERROR=0. dim_variant 101,0k dòng; test accepted_values variant_type PASS (không có '(chưa ánh xạ)'); relationships fct_lines → dim_variant PASS (không có biến thể đã xoá).
- [x] 4 câu `check_variant.sql` (11/11): 1–7/11 units 1.338, line_revenue 41.214,26 không đổi ✓; 226 dòng không có size/loại/đời máy = sản phẩm không có lựa chọn (ornament 'Default Title'...), đúng. Không có '(chưa ánh xạ)' ✓. Ốp 1–7/11: 337 cái (khớp product_daily Phone Case 337 ✓): Samsung 67 (chỉ Standard), iPhone 270 = Standard 58,1% / MagSafe 41,9%; giá TB MagSafe 34,21 vs Standard 31,97 (+7%). Hoodie AUH: AirKnit 82 cái (3.469,33), Heavyweight 8 cái (461,94; TB 57,74 vs 42,31, +36%), Fleece 0.

### Review dim_variant (11/11)
- Tách loại biến thể bằng `selectedOptions` (có tên), không dò chữ hay tách SKU. Bảng tra 5 dòng, test cảnh báo khi shop thêm loại mới. Số tổng không đổi, cộng chéo khớp product_daily.
- [x] Tháng 1/2026 (11/11 09:26 giờ VN): Meta 6 lần gọi, 1%, +76 dòng (ad_insights_daily 19.470); Klaviyo 7 lần gọi, +3 dòng. Reconcile (2 lần gọi Meta): Meta ✓ spend 1.018,38 = 1.018,38, 16 ngày; Klaviyo ✓ Placed Order 4 = 4, 3 ngày. check_raw chỉ báo trễ (dự kiến).
- [x] **Gom lịch sử XONG**: Meta, Klaviyo có 1/1/2026 → 8/11/2026, mọi tháng khớp nguồn. Shopify từ 11/2024.
- [x] (11/11 10:29 giờ VN: Meta 5 lần gọi 1%, Klaviyo 7 lần, check_raw OK) Từ 10:27: `python -m pipelines.run --skip shopify` (7 ngày gần nhất) → check_raw OK → `python -m pipelines.dbt build`.
- [x] (11/11) Dòng con theo tiền tố SKU: seed `product_lines.csv` 17 tiền tố → product_subline + product_line (nhóm lớn, chỉ dùng khi productType trống), source brief/title; `dim_product` thêm product_subline, product_subline_source (brief_line = dòng con nếu source brief); `fct_lines` thêm product_subline; `product_daily` grain ngày × product_line × product_subline. Seed đổi cột nên phải `dbt build --full-refresh`. dbt parse OK (19 model, 96 test). Câu kiểm `checks/sql/check_subline.sql`.
- [x] Huy Anh build --full-refresh + câu 1, 2 (11/11): tổng 1–7/11 vẫn 1.338 cái, 41.214,26 ✓. Long Sleeve: Performance 506 (93,9%), Sun Hoodie 30 (5,6%; TB 40,94 vs 32,15, +27%), 3 cái tiền tố lẻ (dòng con = nhóm lớn); Ornament: Glass 268 (100%, tuần này không bán Ceramic); Short Sleeve: Button-up 41 (62,1%), Pro Tee 25 (37,9%).
- [x] Câu 3: dòng con từ tiền tố suy tên (title) 3.286 sản phẩm, từ brief 1.356, bằng nhóm lớn 258 (tổng 4.900). Khớp đúng số tính trước từ bảng tiền tố.

### Review dòng con (11/11)
- product_line (productType) giữ nguyên, thêm product_subline từ tiền tố SKU (17 tiền tố). Số tổng không đổi. 2/3 sản phẩm dùng nghĩa em suy từ tên → gửi anh Quang duyệt bảng `seeds/product_lines.csv`. Nghĩa tiền tố 'title' (suy từ tên) chờ anh Quang duyệt.
- [x] (11/11) Mã cuối tên sản phẩm Long Sleeve ≠ tiền tố SKU: TBT 370, AOF 198, SRT 24, RT, RS, RW, RB, RM... đều có SKU ULS → chỉ là mã thiết kế/bộ sưu tập (R* có vẻ theo loài cá: RT trout, RW walleye, RB bass, RM musky, RRF redfish, RC crappie, RBC blue catfish). Bảng dòng con vẫn đúng vì tra theo SKU. Tiền tố SKU mới chưa có trong seed: DL0 (~30 sản phẩm, lẫn cả 1 áo nữ PGH02), DL1 (3); 2 sản phẩm không SKU (SG1G, FG1G) → đang rơi vào 'bằng product_line', tuần 1–7/11 chỉ 3 cái. Hỏi anh Quang DL0/DL1 là gì; chưa thêm vào seed.
- [x] (11/11) Quy tắc SKU nháp: macro `sku_prefix` (SKU `DL<số>…-<mã>-…` lấy mã dòng ở phần 2: ULS, FLS, BCT; không có phần 2 thì 3 chữ đầu), dùng ở stg_variants và stg_line_items. Thử 10 ca PASS, dbt parse OK. DL0 toàn DRAFT nên chưa đổi số đã bán.
- [x] Dọn: 7 script dùng một lần chuyển vào `checks/_archive/` (kèm README ghi đã dùng để làm gì): check_shopify_scopes, try_sandbox, inspect_klaviyo, diagnose_meta_day, diagnose_shopify_orders, demo_orders_by_month, drop_old_views. Xoá __pycache__. Không file nào gọi tới chúng; 10 bộ test vẫn PASS.
- [x] Seed thêm BCT,Graphic T-Shirt,T-Shirt,title (18 tiền tố). Huy Anh cần `python -m pipelines.dbt build --full-refresh`.
- [x] Huy Anh `dbt build --full-refresh` (11/11 10:22): PASS=116, WARN=1 (51 dòng ad đã xoá), ERROR=0.

## 12/11
- [x] Huy Anh `python -m pipelines.run` (08:02 giờ VN, `logs/runs.jsonl`): Shopify 19 lần gọi (orders 11.353), Meta 11 lần gọi, mức dùng 2% (ad_insights_daily 19.994), Klaviyo 96 lần gọi, 0%; check_raw OK (dữ liệu mới trong 36 giờ).
- [x] Reconcile 4–10/11 (08:13): Shopify 778 = 778 ✓; Klaviyo Placed Order 779 = 779 ✓; Meta spend 23.697,15 vs kho 23.696,91 ✓ (7 ngày, không ngày lệch).
- [x] `dbt build` (08:15): PASS=116, WARN=1 (51 dòng ad đã xoá, như cũ), ERROR=0. Kho có số tới 11/11.


## Tuần 3: chỉ số chung + cổng khớp số (kế hoạch 12/11, chờ Huy Anh duyệt)

Brief tuần 3: `mart_daily_kpi`, `mart_type_day`, `metrics.yml`, cổng khớp số 7 ngày đã đóng với `dashboard/morning.html`, bảng lệch trong README. Demo: bảng so 7 ngày, mọi dòng lệch < 1% hoặc có lý do.

Đã có sẵn: `daily_performance` có Rev, Orders, Spend, MER, CPO theo ngày Phoenix. Thiếu: AOV, CM ước, spend theo product type, file chỉ số, số của morning.html.

Chặn: trong máy KHÔNG có `dashboard/morning.html`, `context/metrics.md`, `context/cogs.csv` (repo anh Quang). Bước 1–4 làm được ngay; bước 5–6 cần số morning.html.

1. [x] (Huy Anh build + 3 câu kiểm 12/11: 1–7/11 815 đơn, rev 44.319,85, spend 24.098,21 (Meta chỉnh ngày gần, trước 24.098,56), AOV 54,38, MER 1,8391, CM ước 6.127,92; cm_est = rev × 0,682 − spend 10/10 dòng; 11/11 spend null → CM null; câu 3 lệch daily_performance 0 dòng. Ghi nhận: 5/11 CM −294,56, MER hoà vốn ≈ 1,47.) (code 12/11: `models/marts/mart_daily_kpi.sql`, vars `cogs_rate`/`fee_rate` trong dbt_project.yml, mô tả + 4 test trong `_marts.yml`, câu kiểm `checks/sql/check_tuan3_b1.sql`; dbt parse OK 20 model, 100 test; chờ Huy Anh build + kiểm) `mart_daily_kpi` (table, dựng từ `daily_performance`, không tính lại): date, rev, orders, aov = rev / orders, spend, mer, cpo, cm_est = rev × (1 − 0,28 − 0,038) − spend (công thức brief, tạm tới khi có cogs.csv). Spend null thì mer, cpo, cm_est null. Test: unique date, not_null; tổng 1–7/11 vẫn 815 đơn, rev 44.319,85.
2. [x] (Huy Anh build + 3 câu kiểm 12/11: chênh spend fct_ad_day vs daily_performance 1–10/11 = 0; 4–10/11 không có '(chưa gán)', '(không theo type)' 10,35; cộng 11 type = 23.696,91 = reconcile; % có type theo tháng 0/49,9/98,8/99,7. Long Sleeve 43,3% + Phone Case 29,3% spend. Chưa thấy dòng PASS/WARN.) (code 12/11. Dữ liệu thật: tên kiểu mới Catalog-/Static- chiếm 0% spend 1–8/2026, 49,9% 9/2026, 98,8% 10, 99,7% 11; 11 type. Huy Anh chốt: tên kiểu cũ → '(không theo type)', không đoán. Đã làm: seed 11 dòng + test relationships sang dim_product (cảnh báo); fct_ad_day thêm is_typed_name, campaign_type, ad_product_line; test tests/ad_type_chua_gan.sql (cảnh báo); dbt parse OK 20 model, 3 seed, 106 test; câu kiểm checks/sql/check_tuan3_b2c.sql) Seed `campaign_types.csv`: cụm product type trong tên campaign (`<Format>-<Đích>_<Type>_<Audience>`: Sun Hoodie, Hoodie, Long Sleeve, Short Sleeve Shirt, Phone Case, AirPods Case, Ornament, Cardigan, Can Cooler, Quilt) → `product_line` của dim_product. Macro tách phần 2 sau dấu `_`. Không khớp → `(chưa gán)`; test cảnh báo khi có spend `(chưa gán)`.
3. [x] (Huy Anh build + kiểm 12/11, 4–10/11: spend_type = spend_kpi 23.696,91, chênh 0; rev_type 38.823,13 = product_daily, chênh 0; rev_kpi 41.960,20 (lệch 3.137 = ship + thuế). ROAS tuần: Short Sleeve 5,97, Fleece 5,9, Quilt 3,72, Cardigan 3,13, Hoodie 2,51, Ornament 1,86, Long Sleeve 1,58, Phone Case 1,32, AirPods Case 0,45, Can Cooler 0; '(không rõ)' rev 58,58. Bẫy: ROAS theo type gán cả đơn tự nhiên/email và mua chéo cho type; type spend nhỏ thì ROAS cao giả.) (code 12/11: `models/marts/mart_type_day.sql` full outer join rev × spend, spend null ngoài khoảng Meta; 3 test; dbt parse OK 21 model, 109 test; câu kiểm `checks/sql/check_tuan3_b3.sql`; chờ build) `mart_type_day`: ngày × product_line: rev (line_revenue từ fct_lines), spend (fct_ad_day theo campaign type), roas = rev / spend. Kiểm: cộng spend mọi type + `(chưa gán)` = spend daily_performance; cộng rev = line_revenue product_daily.
4. [x] (12/11: `transform/metrics.yml` 10 chỉ số, mỗi chỉ số label/formula/source/grain/sum_rule/traps, status tạm; `tests/test_metrics_yml.py` kiểm nguồn bảng.cột có trong _marts.yml, tỉ lệ CM khớp vars, đã thử ca sai bị bắt; MCP `metric_definitions` đọc metrics.yml thay _marts.yml, test_mcp_server cập nhật; 11/11 bộ test PASS. Tool MCP mới chỉ có hiệu lực ở phiên mới.) `metrics.yml`: mỗi chỉ số (rev, orders, aov, spend, mer, cpo, cm_est, roas theo type) có công thức, nguồn (bảng.cột), ghi chú bẫy (giờ Phoenix, Meta purchase thổi ~1,6×, MER từ tổng, rev ngày cũ giảm khi hoàn, đơn huỷ đang tính). MCP `metric_definitions` đọc file này.
5. [x] BỎ QUA (anh Quang 12/11: "Skip đi em, em có số hệ thống rồi, sao mà lệch được"): không so với morning.html; dùng reconcile với nguồn 4–10/11 (Shopify 778 = 778, Meta 23.697,15 vs 23.696,91, Klaviyo 779 = 779). gate.py giữ lại để dùng sau. (khung xong 12/11: `checks/gate.py` đọc `checks/gate/morning.csv` (7 ngày 4–10/11, ô trống chờ số), query mart_daily_kpi có tham số, lệch % = (kho − morning)/|morning|, dòng 7 ngày MER từ tổng, ghi README giữa dấu gate:start/end, logs/gate.json, mã 1 nếu lệch ≥ 1% chưa lý do hoặc còn ô trống; `tests/test_gate.py` 8 ca PASS với BigQuery giả; 12/12 bộ test PASS. Chờ số morning.html. Huy Anh chạy thật lần đầu 12/11 11:58 với morning.csv trống: query kho OK, README.md được tạo với bảng 7 ngày + dòng tổng (rev 41.960,20, 778 đơn, spend 23.696,91, MER 1,77, CM 4.919,94), báo 35 ô chưa có số, mã 1 đúng.) Cổng khớp số: `checks/gate.py` so mart_daily_kpi với số morning.html 7 ngày đã đóng (Rev, đơn, spend, MER, CM ước), lệch %, cờ ≥ 1%.
6. [x] (12/11: README.md ghi quyết định bỏ morning, bảng reconcile nguồn 4–10/11, bảng 7 chỉ số theo ngày từ mart_daily_kpi) README: bảng lệch 7 ngày + lý do từng dòng lệch ≥ 1%.
7. [x] (code 12/11: performance_summary thêm aov, cm_est (subquery mart_daily_kpi); 5 tool mới type_performance (mart_type_day), product_performance (product_daily, lọc product_line), ad_performance (fct_ad_day, level campaign/adset/ad danh sách cố định, top ≤ 50), email_performance (email_daily, channel), customer_summary (dim_customer theo cohort, rollup tổng, không trả customer_key); tham số có kiểu DATE/INT64/STRING. test_mcp_server 9 tool PASS, 12/12 bộ test PASS. Dry run lần 1: 6/9, ad_performance lỗi tổng của tổng (having sum(spend)), sửa bằng lọc spend > 0 trước group by + test tự dò; dry run lần 2: 9/9 hợp lệ, quét tối đa 3,8 MB. Thử thật phiên mới 12/11, câu 1 'type nào ROAS thấp nhất 4–10/11' ✓: AirPods Case 0,45 (526/1.168), Phone Case 1,32, Long Sleeve 1,58, Ornament 1,86, Hoodie 2,51 khớp check_tuan3_b3; Claude tự nhắc hoà vốn 1,47, ROAS cao giả type spend nhỏ, mua chéo, Can Cooler $37 quá nhỏ để kết luận. Câu 2 (ad của AirPods Case, Phone Case) lộ giới hạn: top 50 ad toàn shop, không lọc được, thiếu ~$2.538 Phone Case và ~$732 AirPods ở ad nhỏ. Sửa 12/11: ad_performance thêm lọc product_line (ad_product_line) và campaign (tên đầy đủ), cờ truncated + ghi chú khi chạm top, ghi chú khi rỗng; test PASS; phiên mới hỏi lại theo campaign Static-Collection_AirPods Case ✓: 41 ad (< 50, không bị cắt), cộng spend 41 ad = 873,25 = check_tuan3_b2 dòng 7; 6 ad tốn mà meta_roas thấp = 351,65 (~40%). Câu 3 (Long Sleeve theo dòng con) số ✓: tổng 16.204 = câu 1, Performance 95,5%, Sun Hoodie $38,9/áo vs $32,0; nhưng Claude gọi dòng con 'Long Sleeve' (fallback khi tiền tố SKU lẻ/chưa có seed) là 'Long Sleeve thường' và kết luận sai. Sửa: product_performance thêm ghi chú dòng con trùng tên nhóm lớn = chưa phân được; test PASS; hiệu lực ở phiên mới. Câu 4 (flow email tháng 10) ✓ nhất quán: 73+17+11+4+1+1 = 107 đơn flow, Welcome v2 68%, đơn/1.000 email tính lại đúng; tỉ lệ mở/click từ tổng; nhắc số Klaviyo tự gán. Phát hiện: 2 flow cũ (Welcome Series, Abanoned Checkout) vẫn gửi song song bản v2/v3, hỏi đội email. Câu 5 (cohort 6–10/2026) ✓ nhất quán: 6.908 khách = cộng 5 cohort, % quay lại gộp 15,0%, LTV gộp 73,26, LTV/đơn mỗi khách ≈ AOV; nhắc cohort mới thấp là bình thường. 2 chỗ chưa chắc: 'AOV không bị ảnh hưởng bởi độ mới' (AOV gộp cả đơn mua lại, đơn huỷ, hoàn), 'Welcome v2 chạy từ 01/10' (không có trong số liệu tool trả); khách mới tháng 10 tăng cùng lúc spend 9→10 tăng 38k→80k. Câu 6 (MER, CM 4–10/11) ✓ đúng từng số: 778 đơn, rev 41.960,20, spend 23.696,91, MER 1,7707, CPO 30,46, AOV 53,93, CM 4.919,95; tự tính giá vốn hoà vốn ≈ 39,7%, giá vốn 35% → CM 1.982,7 (đúng); nhắc thuế trong rev, CM không phải lãi ròng. 6/6 câu thử thật đạt, 2 bản sửa (lọc ad, ghi chú dòng con).) MCP: tool đọc `mart_daily_kpi`, `mart_type_day` (gộp với 4 tool tuần 2 còn dở).
- [x] (12/11) Huy Anh `dbt build` đầy đủ sau tuần 3: PASS=132, WARN=1 (51 dòng ad đã xoá, như cũ), ERROR=0, TOTAL=133 (21 model + 3 seed + 109 test). Test seed campaign_types → dim_product PASS: cả 11 product_line trong seed có thật; ad_type_chua_gan PASS: không campaign kiểu mới nào thiếu seed.
- [x] (12/11) `checks/sql/check_gate_cach_tinh.sql`: orders, rev 4–10/11 theo nhiều cách (bỏ huỷ, total_price lúc đặt, bỏ thuế, bỏ thuế + ship, trừ hoàn theo ngày hoàn, cắt ngày UTC, giờ VN) để tìm lý do khi cổng lệch. Chưa chạy.
- [x] (12/11) PROGRESS.md ghi bù 11/11 và 12/11.

## Áp mô hình phân tích vào hệ thống (kế hoạch 12/11, chờ Huy Anh chọn mô hình đầu)

Chỉ 5 mô hình Huy Anh đã phân tích: 1 Cohort, 2 RFM, 3 CLV, 5 Pareto/ABC, 8 Dự báo + bất thường. KHÔNG làm 4, 6, 7.
Mỗi mô hình 3 bước, làm từng bước như tuần 3 (mình viết, Huy Anh build + kiểm số): bảng gold → định nghĩa + bẫy trong metrics.yml → tool MCP.

- [x] (bước 1 code 12/11: model + 4 test cột + unique + `tests/cohort_hop_ly.sql` (tháng 0 = 100, Wilson bao con số giữa, active ≤ size); Wilson kiểm bằng Python 3/40 → 2,58–19,86 khớp bài học; dbt parse OK 22 model, 114 test; câu kiểm `checks/sql/check_cohort_b1.sql`. Huy Anh build + câu 2 (12/11): cỡ cohort 962/1.373/1.280/798/2.495 = customer_summary; tháng 1 trọn: 6 7,3%, 7 6,9%, 8 8,3%, 9 8,9% (khoảng Wilson chồng nhau); ô tháng 11 (*) thấp vì tháng chưa hết. Huy Anh xác nhận ổn. Bước 2 (12/11): metrics.yml thêm retention_pct, repeat_rate (khác nhau: từng tháng vs tính dồn), _marts.yml thêm mô tả dim_customer.is_repeat; test_metrics_yml PASS 12 chỉ số. Bước 3 (12/11): tool `cohort_retention` (cohort_from/to YYYY-MM, max_offset 1–24, gom theo cohort, cờ small_cohort < 100 khách, ghi chú tháng lịch, khoảng không chồng nhau, ô chưa trọn); metrics.yml thêm bẫy tháng lịch, cohort nhỏ; sửa 2 bẫy cũ bị YAML đọc thành dict + test chặn; 12/12 bộ test PASS, MCP 10 tool. Thử thật phiên mới 12/11 ✓: chọn 5/2026 (10,52%, 53/504) là ứng viên, không chọn 2/2026 (15 khách), nói 6–9 chưa tách được; Claude tự thêm phép so hai tỉ lệ z: 5 vs 9 = 0,97, 5 vs 6 = 2,12, 5 vs 7 = 2,56 (mình tính lại khớp; 5 vs 4 = 3,95) và nhắc so nhiều cặp. Dry run 10/10 hợp lệ, cohort_retention quét 0,0 MB. MÔ HÌNH 1 XONG.) 1 Cohort: `mart_cohort_retention` (cohort tháng × tháng thứ 0, 1, 2...: % quay lại), khoảng tin cậy Wilson cho cohort nhỏ.
- [x] (bước 1 code 12/11 theo bài đã học: R ngưỡng hành vi vars 60/180/365, F 1/2/3+, M ngũ phân vị, 9 nhóm theo thứ tự luật; chỉ đếm đơn không huỷ (khác dim_customer); test unique, accepted_values r_band/segment, tests/rfm_hop_ly.sql; câu kiểm checks/sql/check_rfm_b1.sql (câu 1 kiểm ngưỡng R bằng khoảng cách đơn 1 → 2). Huy Anh build + 3 câu 12/11 (as_of 2026-11-11): 9.341 khách = dim_customer; đơn 1 → 2 của 1.288 khách: p25 7, p50 17, p75 39, p90 78 ngày, 83,9% trong 60 ngày, 99,3% trong 180 (bị thiên ngắn vì shop còn trẻ: khách mới chưa có thời gian quay lại muộn). Nhóm: Ngủ đông 44,2%, Khách mới 39,8%, Mới quay lại 5,4%, Cần chú ý 4,3%, Champions 2,3% (8,3% doanh thu, M TB 258), Đã mất 1,5%, Loyal 1,2%, Không thể để mất 1,0% (F TB 1,36, M TB 118: M=5 là top 20% nên phần lớn là khách 1 đơn to), Có nguy cơ 0,1% (10 khách). Huy Anh chốt: giữ ngưỡng 60/180/365 và luật 'Không thể để mất' như bài học, ghi bẫy ở bước 2. Bước 2 (12/11): metrics.yml thêm rfm_recency, rfm_frequency, rfm_monetary, rfm_segment kèm bẫy (ngưỡng thiên ngắn, M=5 là top 20%, Có nguy cơ ít do shop trẻ, chưa backtest); test PASS. Bước 3 (12/11): tool `rfm_segments` (không tham số, chỉ số tổng theo nhóm, không customer_key; kèm luật gán nhóm, cờ nhóm < 30 khách, ghi chú ảnh chụp, chưa backtest); MCP 11 tool, 12/12 bộ test PASS. Dry run 11/11 hợp lệ, rfm_segments quét 0,5 MB. Thử thật phiên mới 12/11 ✓: Champions 2,3% khách / 8,3% doanh thu / $258, Có nguy cơ quá nhỏ, nhắc chưa backtest, nhắc Ngủ đông 37,6% là tiền quá khứ; tự nối email_performance (Sunset 625 email 0 đơn, chưa có flow winback). 2 chỗ yếu: không nói rõ Không thể để mất phần lớn là khách 1 đơn to; dùng retention cohort 2–4% cho Ngủ đông (cohort gồm cả khách mua nhiều lần, nên lạc quan hơn thật). CHƯA XONG theo Huy Anh 12/11 ("làm 1 mô hình chắc không sai rồi hẵn sang mô hình mới"): còn backtest `checks/sql/check_rfm_backtest.sql` (mốc 1/7 và 1/8/2026, % mua lại 90 ngày theo nhóm + Wilson) và dòng PASS/WARN build. Build 12/11: PASS=8 (1 model + 7 test) WARN=0 ERROR=0 ✓. Backtest 12/11 ✓: % mua lại 90 ngày mốc 1/7 / 1/8: Champions 32,5 / 37,3, Mới quay lại 18,7 / 20,4, Khách mới 9,4 / 9,4, Ngủ đông 4,0 / 4,1, Đã mất 1,4 / 2,1, cùng thứ tự; 4 nhóm đầu tách nhau (Wilson không chồng mốc 1/8), Ngủ đông vs Đã mất chưa tách; Loyal, Cần chú ý, Không thể để mất, Có nguy cơ quá nhỏ (0–63 khách). Đưa vào metrics.yml + ghi chú tool; Ngủ đông mức nền ~4%/90 ngày. MÔ HÌNH 2 XONG.) 2 RFM: `mart_rfm` (điểm R, F, M từ dim_customer, chia nhóm khách). Không trả customer_key qua MCP, chỉ số tổng theo nhóm.
- [x] 3 CLV (bài học 3 cấp: 1 lịch sử từ cohort, 2 công thức nhanh KHÔNG dùng, 3 BG/NBD + Gamma-Gamma bằng Python). Phát hiện: shop gần như chưa có khách trước 2026, cohort đủ 12 tháng rất nhỏ nên CLV 12 tháng chưa đo đáng tin. Bước 1 code 12/11: `mart_cohort_clv` (cohort × tháng k: trung bình, trung vị, CI 95%, bội số so tháng 0), test unique + not_null + `tests/clv_hop_ly.sql` (cộng dồn không giảm, tháng 0 bội số 1, cỡ khớp retention, CI bao trung bình); dbt parse OK 24 model, 126 test; câu kiểm `checks/sql/check_clv_b1.sql` (câu 3 khớp tổng rev có email). Huy Anh chạy 12/11: câu 1 cohort đủ 12 tháng chỉ ~144 khách (11/2024 52, 12/2024 74, 2025 lẻ tẻ), KHÔNG có cohort 8–12/2025 (hỏi anh Quang); câu 2 trung vị ~$46 mọi ô (khách điển hình 1 đơn), bội số tháng 5: 4/2026 ×1,16, 5/2026 ×1,24 (CI chồng); câu 3 lệch −2,58/673.861; kiểm từng cohort 18/18 lệch nằm trong giới hạn làm tròn (0,005 × số khách) ✓. Build PASS=6 (1 model + 5 test gồm clv_hop_ly) WARN=0 ERROR=0 ✓. BƯỚC 1 XONG. Huy Anh chốt 12/11: HOÃN cấp 3 (BG/NBD + Gamma-Gamma) vì chưa có trọn 1 năm khách (từ 4/2026), chưa qua BFCM, holdout 180 ngày lùi về lúc mới ~1.200 khách, chưa thử thư viện Python; quay lại sau 2/2027. Làm trọn cấp 1: bước 2 metrics.yml, bước 3 tool clv_summary (kèm CAC khách mới = spend / first_orders để so CLV). Bước 2 (12/11): metrics.yml thêm clv_hist, clv_median, clv_multiple kèm bẫy (CLV doanh thu, 12 tháng chưa đo, trung vị ~$46, ×1,16–1,24 sau 5 tháng); test PASS. Bước 3 (12/11): tool `clv_summary` (cohort_from/to, max_offset ≤ 24; CLV doanh thu trung bình/trung vị/CI/bội số, CAC khách mới = spend Meta cả tháng / cỡ cohort (null nếu tháng thiếu Meta), clv_margin_est = CLV × (1 − cogs − fee) đọc từ vars dbt, tỉ lệ CLV lợi nhuận ước / CAC); MCP 12 tool, 12/12 bộ test PASS. Dry run 12/12 hợp lệ (clv_summary 0,0 MB). Thử thật phiên mới 12/11 ✓: gộp 7 cohort 4–10/2026 = 8.026 khách, spend 273.157,59, CAC 34,03; doanh thu tháng 0 TB 64,61 (mình tính lại khớp); CAC 9/2026 47,77, 10/2026 32,16; nêu trung vị 46 × 0,682 ≈ 31 < CAC 34 (khách điển hình hoà/lỗ); nhắc CAC hơi cao, lợi nhuận hơi cao, chỉ Meta, bỏ cohort < 100. MÔ HÌNH 3 (cấp 1) XONG.
- [x] (bước 1 code 12/11 theo bài đã học: đơn vị mẫu, line_revenue, cửa sổ 90 ngày, tập hợp = mẫu đang mở bán kể cả 0 cái ∪ mẫu có bán; nhóm A/B/C/D + Mới (< 30 ngày); abc_in_line xếp riêng từng dòng; rev_per_live_day; bỏ đơn huỷ và dòng không phải sản phẩm (UpCart/Shipping Protection/Gift Card theo tên); vars abc_*; test unique, accepted_values, tests/abc_hop_ly.sql; dbt parse OK 25 model, 134 test; câu kiểm checks/sql/check_abc_b1.sql (khớp nguồn, dòng bị tách, bảng ABC, top 1/5/10%); XYZ để sau khi ABC chắc đúng. Build 12/11: PASS=9 WARN=0 ERROR=0. 4 câu kiểm lần 1: chenh 0 nhưng lộ 3 lỗi: (1) 'gift card' khớp nhầm 'Seed Gift Cardinal Pair' (ornament thật); (2) mẫu đã xoá mất product_id bị tách (~$446 T-Shirt); (3) Mới (1.818 mẫu, 43,6%) chen vào thứ hạng nên A chỉ 77,2%. Top 1/5/10% = 17,4/42,4/56,7% (còn gồm Mới). Sửa: regex cả cụm + ^tip$, product_key cho mẫu đã xoá, xếp hạng riêng trong mẫu đủ tuổi; thêm câu 5 kiểm created_date (1.818 mẫu mới có thật không). dbt parse OK. Build lại PASS=9 WARN=0 ERROR=0. 5 câu lần 2 ✓: chenh 0, bi_tach 496,95 chỉ Tip + Gift Card; mẫu đủ tuổi 2.360: A 407 (17%) = 80,0% doanh thu đủ tuổi, B 15,0%, C 5,0%, D 1.021 (43%) 0 cái; Mới 1.819 (7,4% doanh thu); top 1/5/10% mẫu đủ tuổi có bán (1.339) = 15,9/40,4/55,2%; created_date trải đều 100–270 mẫu/ngày đăng nên Mới là thật. Kiểm định viết 12/11: `checks/sql/check_abc_on_dinh.sql` (câu 1 ma trận chuyển nhóm K1 = 90 ngày trước → K2; câu 2 Gini 3 tập); công thức Gini thử bằng Python (đều = 0, 1 mẫu gánh hết = 0,99, [1..5] = 0,267). Kết quả 12/11: A K1 (156) → A 53,2% / B 26,9% / C 10,9% / D 7,1% / ẩn 1,9% (80% vẫn A hoặc B, dưới ngưỡng 60% giữ A mình đặt); B K1 (189) chia đều (D 28%); C K1 (207) → D 36,2% + ẩn 28% (gần chết). Gini mẫu có bán K1 0,683 (552 mẫu) → K2 0,659 (1.339); K2 kể cả D 0,806 (đúng mức POD ≥ 0,8 của bài học). Kết luận: ABC đúng và đã kiểm định; quyết định từng mẫu chỉ với A (xem kèm B), B/C quyết ở cấp chủ đề. Bước 2 (12/11): metrics.yml thêm abc_class, abc_revenue, abc_concentration kèm bẫy từ kiểm định; test PASS. Bước 3 (12/11): tool `product_abc` (product_line tuỳ chọn → abc_in_line, top ≤ 50; nhóm A..Mới kèm % doanh thu đủ tuổi và % tổng, Gini kể cả D, top mẫu đủ tuổi kèm tên + link, top 10 mẫu mới theo rev_per_live_day, ghi chú kiểm định); 4 câu SQL; MCP 13 tool, 12/12 bộ test PASS. Dry run 16/16 hợp lệ. Thử thật phiên mới 12/11 ✓: A 407 (17%) 80%, D 1.021 (43%) kèm 'có thể chưa ai thấy', nhắc ads, Gini 0,81, top Santa Mahi Mahi Express ULS638K $8.813. 3 chỗ yếu: (1) so Mới 7,4% doanh thu với mẫu đủ tuổi không công bằng (Mới < 30 ngày vs 90 ngày, phải dùng rev_per_live_day), 'mẫu mới sẽ thành D' chưa có số; (2) dùng 7% A→D để biện cho D hồi phục (ngược chiều, chưa có số D→A); (3) top 20 toàn Long Sleeve không nối với Long Sleeve 43% spend Meta (vòng lặp ads). MÔ HÌNH 5 (ABC) XONG. XYZ bước 1 code 12/11 (Huy Anh chọn làm trước mô hình 8): macro `is_non_product` dùng chung (mart_product_abc đổi sang macro, logic không đổi); `mart_product_xyz` (mẫu đủ tuổi có bán, 12 tuần trọn = 84 ngày cuối, chỉ tuần đã mở bán trọn, cv = sd/mean doanh thu tuần, X < 0,5 / Y 0,5–1 / Z > 1, chưa đủ dữ liệu khi < 10 cái hoặc < 8 tuần; vars xyz_*); test unique, accepted_values, tests/xyz_hop_ly.sql; dbt parse OK 26 model, 140 test; câu kiểm checks/sql/check_xyz_b1.sql. Build PASS=16 (ABC build lại với macro + XYZ) WARN=0 ERROR=0. Kết quả: chênh −2.590,95 (0,9%, tuần mẫu chưa mở bán trọn, đúng thiết kế); chỉ 147 mẫu đủ dữ liệu (A có 260/407 chưa đủ), cv p10 0,67 / p50 1,02 / p90 1,60, chỉ 4 mẫu X: cấp mẫu đo NHIỄU (Poisson cv ≈ 1/√(cái/tuần)). Soi AX/AZ bằng mắt thì nhãn đúng. Huy Anh chốt: gộp lên dòng con + biến thể (đúng đơn vị trong bài học), giữ bảng cấp mẫu kèm cảnh báo. Code 12/11: `mart_xyz_group` (cap_do dòng con / biến thể, tuần từ lần bán đầu của nhóm, cv, noise_cv, trend_ratio, chưa đủ dữ liệu khi < 5 cái/tuần hoặc < 8 tuần), test unique, accepted_values, tests/xyz_group_hop_ly.sql (tổng dòng con khớp nguồn); câu kiểm checks/sql/check_xyz_group_b1.sql. Build lần 1: ERROR=1 ở test xyz_group_hop_ly (nghi: nhóm ra đời giữa cửa sổ bị bỏ tuần đầu, test lại so tổng cả tuần đó). Sửa: thêm first_sale_date, test so từng dòng con đã có bán trước cửa sổ và in tên nhóm lệch; câu kiểm 3 liệt kê nhóm ra đời trong cửa sổ. Build lại PASS=8 WARN=0 ERROR=0 (dòng con có bán trước cửa sổ khớp nguồn từng nhóm). 3 câu kiểm 12/11 ✓: câu 3 có 11 nhóm ra đời trong cửa sổ (Tough Phone Case 19/9, Glass Ornament 4/10...) xác nhận nguyên nhân lỗi lần 1. Performance Long Sleeve X (cv 0,24, noise 0,05, trend 1,36, 13–22k/tuần, riêng tuần 3 ~10–16/9 tụt 8.440: tín hiệu cho mô hình 8); Sun Hoodie X trend 0,82; Pro Short Sleeve Tee X trend 0,56 (giảm nửa); Performance Hoodie Y cv 0,93 trend 8,06 (mùa vụ, đúng Y bài học); Button-up Y; Phone Case, Glass Ornament chưa đủ tuần (7, 5). Kết luận: XYZ cấp gộp đo được hành vi thật (noise_cv 0,05–0,2 ≪ cv); PHẢI đọc kèm trend_ratio. Bước 2 (12/11): metrics.yml thêm xyz_class, xyz_trend (đọc kèm trend, không đọc cấp mẫu, so noise_cv); 24 chỉ số PASS. Bước 3 (Huy Anh chọn thêm vào product_abc): ABC_XYZ_SQL đọc mart_xyz_group lọc product_line, trả xyz_by_group + 2 ghi chú; 12/12 bộ test PASS. Dry run 17/17 hợp lệ. Thử thật phiên mới 12/11 ✓: Long Sleeve X ×1,36, Hoodie Y ×8,06 vào mùa, Short Sleeve Tee ×0,56 hết mùa, Sun Hoodie ×0,82, Phone Case/Ornament chưa đủ tuần, không xếp XYZ từng mẫu; tự nhắc 12 tuần chưa chứng minh mùa lặp lại, ads chưa nối mẫu, không có quý 4/2025 để so. 2 chỗ suy luận hơi mạnh: 'Hoodie tăng ×8 dù ads ít nghĩa là khách tự tìm đến' (còn email, catalog chung), 'Ornament sẽ tắt sau tháng 12' (chưa có năm trước). XYZ XONG → MÔ HÌNH 5 XONG HẲN) 5 Pareto/ABC: `mart_product_abc` (xếp sản phẩm/mẫu theo doanh thu, % cộng dồn, nhóm A/B/C).
- [x] 8 Bất thường + dự báo: `mart_daily_anomaly` (so mỗi ngày với mức thường, đánh dấu ngày lạ), dự báo sau.


## Mô hình 8: Bất thường + Dự báo (12/11)

Huy Anh chốt: làm BẤT THƯỜNG trước (SQL trong dbt), dự báo ETS (Python) sau; theo dõi đủ 9 chỉ số; mốc = trung vị 8 ngày cùng thứ.

### Phần A: bất thường
- [x] Bước 1 (viết): vars `anomaly_*` (dbt_project.yml), `mart_anomaly_daily` (9 chỉ số × ngày đã trọn từ 1/3/2026; trung vị + MAD 8 ngày cùng thứ, sàn nhiễu theo loại chỉ số; để ý ≥ 3,5, cần xử lý ≥ 6 hoặc 2 ngày liền), mô tả + test trong `_marts.yml`, `tests/anomaly_hop_ly.sql`, `checks/sql/check_anomaly_b1.sql` (4 câu).
- [x] Huy Anh build + chạy câu 1, 2, 4 (12/11). Câu 4 tính tay khớp (trung vị 71,5, MAD 30,5, sàn √71,5 = 8,46, score 0,45). Câu 1: spend báo 16%, gross 10,5%, orders 10%, email 8,4%, còn lại ≤ 3%. Câu 2: 29% ngày có báo, 31 ngày "cần xử lý".
- [x] LỖI: 11/11 (mới nạp tới 18h Phoenix) bị coi là ngày trọn vì dùng current_date lúc build. Sửa: chỉ lấy ngày < ngày của đơn mới nhất đã nạp; test sửa theo. Cần build lại.
- [x] Câu 3 XÁC NHẬN nghi vấn: phần lớn "cần xử lý" là ĐỔI MỨC, không phải ngày lạ. 10/10–27/10 orders, gross, spend cùng "cao" gần 3 tuần (spend lên ~3.400 từ ~1.500); 27–29/4 shop từ ~6 lên ~40 đơn; 17–31/7 spend lên mức mới. Mốc 8 tuần cùng thứ chạy theo mức cũ suốt nhiều tuần.
  Báo động trông thật: 14/9 CPO 65,77 so với 27 (×2,4, cùng tuần Long Sleeve tụt 10–16/9); 11–12/9 spend giảm 39–52%; 13/5, 21/5 tỉ lệ khách mới tụt 0,56–0,62 so với 0,97.
  email_orders báo vào ngày gửi campaign (20/9, 4/8, 20/10): chuyện đã biết, cần lịch sự kiện.
- [x] Sửa mốc (Huy Anh chọn 12/11): expected = level_7d (TB 7 ngày ngay trước) × weekday_factor (trung vị giá trị ÷ mức của 8 ngày cùng thứ); độ rộng = level_7d × 1,4826 × MAD hệ số, vẫn có sàn nhiễu. Câu 3, 4 viết lại theo cột mới.
- [x] Huy Anh build lại + chạy 4 câu (12/11). Câu 4 tính tay khớp (level 112,43, hệ số 0,9907, expected 111,38, MAD 0,1532, score 0,57). % ngày có báo 29% → 11,5%; "cần xử lý" 31 → 5 ngày; 10–27/10 chỉ còn báo 10/10 (ngày spend gấp đôi) và 14/10 MER.
- [x] LỖI: cancel_rate MẤT HẲN khỏi bảng (câu 1 chỉ 8 chỉ số), refunds còn 54 ngày, email 97: chỉ số hiếm có mức 7 ngày = 0 nên ratio không chia được. Sửa: method 'TB 28 ngày' cho 3 chỉ số hiếm (expected = TB 28 ngày, sàn nhiễu quyết); test thêm thieu_chi_so; câu 5 kiểm tuần 10–16/9.
- [x] Huy Anh build lại + chạy câu 1, 2, 3, 5 (12/11). Đủ 9 chỉ số ✓; refunds 227 ngày, cancel 204, email 204 ✓. % ngày có báo 11,5% (26/227), "cần xử lý" 6 ngày.
  "(không tính được)": refunds 35 ngày (29/3–2/5), cancel 12 ngày (21/4–2/5) = trước khi orders có expected (từ 3/5), nên sàn nhiễu (cần đơn kỳ vọng, AOV kỳ vọng) chưa có. Đúng nhãn, để vậy.
  Câu 5 (10–16/9): 14/9 CPO 65,77 so với kỳ vọng 37,14 (+77%) chỉ score 3,21 → bình thường (ngưỡng 3,5). Shop lúc đó ~25 đơn/ngày nên CPO 1 ngày nhiễu lớn. Bắt được: 11/9 spend −36% (để ý), 10/9 hoàn 336 so với 23 (để ý). Cả tuần orders thấp hơn kỳ vọng 5/7 ngày (−30 đến −46%) nhưng không ngày nào vượt ngưỡng: kiểu tụt TỪ TỪ mà bài học nói cách theo ngày bỏ sót (cần điểm gãy/CUSUM).
- [x] Huy Anh chốt GIỮ 3,5 (12/11). 14/9 ghi là giới hạn đã biết; tụt từ từ cả tuần để cho điểm gãy/dự báo (phần B).
- [x] Hiệu chỉnh: chỉ số nào báo > 10% số ngày thì xem lại sàn nhiễu/ngưỡng; đối chiếu các ngày "cần xử lý" với chuyện thật.
- [x] Bước 2: metrics.yml thêm anomaly_expected, anomaly_score, anomaly_level (27 chỉ số); test_metrics_yml PASS, test_mcp_server PASS.
- [x] Bước 3 (viết): tool `anomaly_check(until="", days=1)` (14 tool). Trả data_checks (bảng cũ hơn hôm qua, ngày thiếu Meta, thiếu chỉ số) TRƯỚC, latest_day đủ chỉ số, alerts xếp cần xử lý → để ý, |score| lớn; mỗi dòng có meaning (chiều nào là xấu). days chặn 31. Test 7f; 12 bộ test máy PASS; thêm vào check_mcp_sql (18 câu).
- [x] Lần thử (2) lặp lại bản ngắn: vẫn nói "MER 1,06 gần như hoà vốn tiền quảng cáo" (2 lần). Sửa tận gốc: notes của anomaly_check nêu MER hoà vốn ≈ 1,47 (1 ÷ biên 0,682 đọc từ vars), dưới mức này là lỗ; test kiểm. PASS.
- [x] Huy Anh dry run (12/11): 18/18 câu SQL hợp lệ, anomaly_check quét 0,2 MB.

### Review phần A (12/11): XONG
Đủ 5 tiêu chí: build + test (9 chỉ số, test đủ chỉ số, ngày trọn); câu kiểm khớp (tính tay 2 lần); kiểm định (29% → 11,5% ngày có báo sau khi đổi mốc, "cần xử lý" 31 → 6, đều giải thích được); dry run 18/18; thử thật 2/2.
Sửa trong lúc làm: ngày chưa trọn theo đồng hồ build; mốc 8 tuần cùng thứ bám mức cũ khi shop tăng; chỉ số hiếm mất im lặng; câu báo "chưa nạp" sai lý do; Claude 2 lần gọi MER 1,06 là hoà vốn.
Giới hạn đã biết: tụt từ từ cả tuần (10–16/9) không báo; 14/9 CPO +77% chưa tới ngưỡng; chưa có lịch sự kiện.
- [x] Thử câu (1) "hôm qua có gì lạ" (12/11): ĐẠT. Claude đọc data_checks trước (kho tới 10/11, 11/11 chưa có), 10/11 cả 9 chỉ số bình thường, tự nêu hoàn +83% nhưng $51 nằm trong nhiễu, đơn +13% mà doanh số −6% (AOV ~50 so với ~60) kéo MER −12%. Lỗi nhỏ: data_checks bảo "chưa nạp hoặc chưa build", thật ra 11/11 ĐÃ nạp dở (18h Phoenix) và bị bỏ có chủ đích. Sửa câu báo (nêu lý do nạp dở, chạy lại sau 14h giờ VN); test sửa theo, PASS.
- [x] Thử câu (2) "tuần 10–16/9" (12/11): ĐẠT. Claude tự nói chuyện chính là cả tuần bán ít (đơn −34%, rev −36% so với 3–9/9) mà tool KHÔNG bắt vì so với 7 ngày trước cũng đã thấp; tự dùng daily_performance so 2 tuần; nêu 10/9 hoàn $336, 11/9 spend −36%, 16/9 spend +40%; tự nêu 14/9 CPO $65,8 không bị báo. Hai chỗ hơi lệch: "MER 1,06 gần như hoà vốn tiền quảng cáo" (hoà vốn thật cần MER ≈ 1,47 sau giá vốn, phí, nên 1,06 là LỖ); "spend −28% mà đơn −34% nghĩa là ads kém hơn" (có thể, nhưng còn khách tự nhiên, mùa vụ).
- [x] Thử thật phiên mới (kế hoạch): (1) "Hôm qua có gì lạ không?" (2) "Tuần 10–16/9 có gì bất thường?". Kỳ vọng: (1) đọc data_checks trước, kể theo chỉ số gốc; (2) nêu 11/9 spend tụt, 10/9 hoàn, VÀ nói cách theo ngày không bắt được orders tụt cả tuần, 14/9 CPO +77% chưa tới ngưỡng.

### Phần B: dự báo (sau khi A đạt)
- [x] Huy Anh cài statsmodels 0.15.0 (12/11), không bị Application Control chặn; ETSModel + khoảng 80% chạy được. Ghim vào requirements.txt.
- [x] Huy Anh chọn so CẢ HAI loại: không điều kiện (naive_season, level_weekday = expected phần A, ets M/Ad/M 84 ngày) và có điều kiện (spend_reg: log đơn ~ log spend + thứ, 56 ngày, dùng spend thật của 14 ngày tới).
- [x] Viết `forecast/backtest.py`: mốc cách 7 ngày, tối đa 16 mốc, dự báo 14 ngày; WAPE, bias, MAE, độ phủ 80%, thắng naive %, theo tầm xa 1–7 / 8–14; WAPE từng mốc. Không ghi BigQuery. `tests/test_forecast.py` PASS (7 ca: đúng khi không nhiễu, đúng ngày cùng thứ, KHÔNG NHÌN TRƯỚC, mốc, spend đổi bậc, độ phủ 60–97%, so trên cùng ô). Chạy thử CLI bằng CSV giả OK.
- [x] Huy Anh `python -m forecast.backtest` (12/11): 255 ngày (1/3–10/11), 16 mốc 14/7–27/10.
  WAPE 1–14 ngày: naive 27,5 | level_weekday 27,0 (+1,8%) | ETS 22,9 (+16,7%) | spend_reg 20,5 (+25,5%). 1–7 ngày ETS = spend_reg (19,4 vs 19,5); 8–14 ngày spend_reg hơn hẳn (21,5 vs 26,3).
  → ETS THẮNG mốc ngây thơ ở cả 2 tầm xa. Mốc phần A (level_weekday) làm dự báo gần như không hơn naive.
  Độ phủ 80%: ETS 72,3, spend_reg 72,3 → khoảng hơi HẸP (tự tin quá mức một chút). Bias âm mọi mô hình (−3 đến −9%): shop đang tăng nên đoán thấp.
  Mốc tệ: 1/9 (naive 63, ETS 57, reg 42: cửa sổ chứa cắt ngân sách 8/9 + tuần tụt 10–16/9), 8/9–6/10 đều 30–50%, kể cả spend_reg 23–38 → tháng 9 hiệu quả ads đổi mạnh, biết spend cũng không đủ. 13/10 ETS 7,8.
  Giới hạn: 16 mốc với cửa sổ 14 ngày chồng nhau, không độc lập; chưa có Q4.
- [ ] Chốt với anh Quang chỗ lưu bản dự báo cũ (Sandbox xoá bảng sau 60 ngày, không MERGE).
- [x] Huy Anh CHỐT dùng cả hai (12/11): ETS cho "nếu cứ như hiện tại" + pacing tháng; spend_reg cho "nếu chi X USD/ngày" (chỉ trong khoảng spend đã thấy).
- [x] Bước B2 (viết): `calibrate` + `calibration_table` trong backtest.py. k = phân vị 80% của hệ số nới cần thiết trên thang log, ước CUỐN CHIẾU từ các ngày đã biết tại mốc (date ≤ mốc, ≥ 4 mốc trước); k_cuoi = k dùng thật. Test 8 PASS (khoảng hẹp một nửa: 50% → ~80%, k ≈ 2; đổi số sau mốc không đổi k).
- [x] Huy Anh chạy lại (12/11). WAPE giữ nguyên. Chỉnh khoảng (12 mốc từ mốc thứ 5): ETS phủ 63,7 → 67,9, k_cuoi 1,26; spend_reg 67,3 → 72,6, k_cuoi 1,28. CHƯA tới 80: k ước từ tháng 7–8 (yên) nên quá nhỏ cho tháng 9 (sai số lớn hẳn). Sai số không ổn định theo thời gian, chỉnh cuốn chiếu luôn trễ một nhịp.
- [x] LỖI: độ phủ ETS ra 72,3 rồi 70,5 giữa 2 lần chạy (khoảng của ETS lỗi nhân tính bằng mô phỏng ngẫu nhiên). Sửa: cố định hạt giống (SEED), 2000 lần mô phỏng; chạy 2 lần trên CSV giả ra đúng số.
- [x] Huy Anh chốt (12/11): dùng k_cuoi (≈1,3, ước lại mỗi lần chạy từ backtest mới nhất), gọi là khoảng 80% nhưng GHI RÕ kiểm ngoài mẫu chỉ phủ ~70%, thị trường đổi (như tháng 9) thì hẹp hơn.
- [x] Huy Anh chọn tầm xa 35 ngày cho ETS, ghi rõ 15–35 ngày ít chắc hơn (12/11). Backtest thêm bảng ETS 35 ngày (WAPE, bias, độ phủ gốc/với k theo 1–14, 15–28, 29–35) + sai số TỔNG 30 ngày từng mốc (thứ pacing cần). Seed cố định; test PASS; chạy CSV giả OK.
- [x] Huy Anh chạy lại (12/11). Số cũ giữ nguyên (seed: ETS phủ 70,5 cả 2 lần ✓). ETS 35 ngày: WAPE 26,3 / 37,8 / 45,0 (1–14 / 15–28 / 29–35), bias −6,5 / −18,2 / −23,9 (đoán thấp ngày càng nặng: xu hướng hãm trong lúc shop tăng), phủ với k 79,9 / 71,0 / 69,6.
  Tổng 30 ngày: trung bình |lệch| 24%, bias −6,7%; tốt (±10%) ở 6–8/2026, tệ ở 8/9–6/10 (−24 đến −63%: spend lên gấp đôi 10/10 mà ETS không biết; 11/8, 1/9 đoán cao +34, +37%: cắt ngân sách 8/9).
  → ETS một mình KHÔNG hợp cho pacing tháng: sai số tháng bị quyết định bởi thay đổi ngân sách, thứ ETS không thấy.
- [x] Huy Anh chọn thêm spend_hold (12/11). Viết: f_spend_hold (spend_reg, spend tới = TB 7 ngày cuối); vào bảng 14 ngày, chỉnh khoảng, và bảng 35 ngày + tổng 30 ngày so cạnh ETS (cùng mốc). Test 3b: spend_hold không nhìn spend tương lai. PASS.
- [x] Huy Anh chạy lại (12/11). spend_hold THUA: 14 ngày WAPE 30,5 (tệ hơn cả naive 27,5, −10,9%), phủ gốc 51,8 (k 1,82); tổng 30 ngày lệch TB 28,8% vs ETS 24,0%. Số cũ giữ nguyên.
  Vì sao: hệ số spend → đơn học trên 8 tuần trôi theo hiệu quả ads; giữ spend cố định 30 ngày không cứu được. ETS bám đà đơn tốt hơn. Kết luận: KHÔNG có dự báo tháng không điều kiện nào tin được (±24–29%, tệ nhất ±63%) ở dữ liệu hiện tại.
- [x] Huy Anh chốt CHỈ 14 NGÀY (12/11): bỏ spend_hold (ghi lý do trong code); bảng 35 ngày giữ để theo dõi (xem lại sau Q4). Pacing tháng chỉ trả lời khi tháng còn ≤ 14 ngày (thật đã có + ETS phần còn lại); sớm hơn thì nói thẳng chưa đoán được, gợi ý hỏi theo kịch bản spend.
- [x] Bước B3 (viết): `forecast/publish.py` chạy backtest để ước k mới nhất, rồi ghi đè 2 bảng gold bằng load job JSONL WRITE_TRUNCATE: `forecast_daily` (14 dòng ETS: fc, lo, hi đã nhân k, train_from/to, WAPE + độ phủ backtest), `forecast_spend_model` (1 dòng hệ số spend_reg, sigma, t80, k, spend_min/max đã thấy, spend 7 ngày). Kiểm số dòng sau khi ghi. `tests/test_forecast_publish.py` PASS (hệ số lưu tính lại ĐÚNG số của mô hình backtest).
- [x] Huy Anh `python -m forecast.publish` (12/11): mốc 10/11, ETS 14 ngày (11–24/11) tổng ~1.805 đơn (~129/ngày, mức 7 ngày 112), k_ets 1,3, k_spend 1,28, hệ số log spend 0,882 (spend +1% → đơn +0,88%: lợi suất giảm dần). 2 bảng ghi đủ 14 + 1 dòng.
- [x] Bước B4 (viết): tool `forecast_orders(spend_per_day=None)` (15 tool). Trống = ETS 14 ngày + pacing tháng CHỈ khi tháng còn ≤ 14 ngày (thật đã có + ETS phần còn lại, khoảng cộng từ khoảng ngày nên rộng hơn thật); có số = kịch bản spend_reg (cùng công thức backtest), ngoài [spend_min, spend_max] thì ToolError; dự báo cũ > 8 ngày thì data_checks. Test 7g. Khai báo 2 bảng forecast là source schema gold trong _sources.yml; metrics.yml thêm forecast_orders, forecast_spend_elasticity (29 chỉ số). 14 bộ test máy PASS; check_mcp_sql thêm 3 câu (21).
- [x] Thử câu (1) "2 tuần tới" (12/11): ĐẠT phần chính (~1.805 đơn, nhịp thứ, phủ thật ~70%, chưa có Q4, BF 27/11). 2 lỗi: (a) so 11/11 "thực tế 92 đơn" với dự báo 115 rồi kết luận "mô hình lạc quan", nhưng 92 là số NẠP DỞ (tới 18h Phoenix); (b) tự cộng lo/hi thành "1.400–2.200" (rộng hơn thật). Sửa: notes nêu ngày đầu dự báo có thể nạp dở + không tự cộng khoảng; test kiểm. PASS.
- [x] Huy Anh `python -m pipelines.dbt parse` (kiểm source mới) + `python checks/check_mcp_sql.py` → 21/21?
- [x] Thử thật phiên mới: (1) "2 tuần tới bán khoảng bao nhiêu đơn?" (2) "Tháng 11 có đạt 3.500 đơn không?" (3) "Nếu giảm spend còn 3.000/ngày?" (4) "Nếu chi 10.000/ngày?". Kỳ vọng: (2) nói chưa đoán được tổng tháng (còn > 14 ngày), (4) từ chối vì ngoài khoảng, (1)(3) nêu khoảng + giả định + chưa có Q4.

## Tiếp ngày 13/11 (dừng 12/11 tối)
Mô hình 8: phần A (bất thường) XONG. Phần B (dự báo) đã có backtest, publish (2 bảng gold đã ghi), tool forecast_orders; còn:
1. Huy Anh `python -m pipelines.dbt parse` (source forecast mới) + `python checks/check_mcp_sql.py` → 21/21.
2. Thử thật trong PHIÊN MỚI (bản tool đã sửa ghi chú nạp dở + không tự cộng khoảng): câu (1) lại cho chắc, rồi (2) tháng 11 đạt 3.500? (phải nói chưa đoán được), (3) spend 3.000/ngày (có số + giả định), (4) 10.000/ngày (phải từ chối).
3. Đạt cả thì viết review phần B, đánh dấu mô hình 8 XONG → cả 5 mô hình (1, 2, 3, 5, 8) xong.
4. Còn treo, hỏi anh Quang: chỗ lưu bản dự báo cũ / snapshot RFM (Sandbox xoá bảng 60 ngày, không MERGE); cogs.csv; lịch sự kiện (sale, lễ, ngày gửi campaign).
Nhịp chạy: sau pipelines.run + dbt build, mỗi tuần chạy `python -m forecast.publish`.
- [x] 13/11: thử lại câu (1) trong phiên mới (mốc 11/11, ~1.851 đơn 12–25/11): ĐẠT. Hết 2 lỗi hôm qua: chỉ so ngày đã trọn (29/10–11/11 = 1.633), không tự cộng lo/hi. Tự nêu luôn câu (2): tổng tháng 11 chưa đưa được (còn 19 ngày). Độ phủ ngoài mẫu giờ ~74%.
  Chỗ hơi lệch: lấy WAPE ngày (23%) làm sai số cho TỔNG 14 ngày ("1.400–2.300"). Backtest chưa đo sai số tổng 14 ngày; cần thêm để tool đưa con số đúng.
- [x] 13/11: câu (3) spend 3.000/ngày: ĐẠT, tốt hơn kỳ vọng. ~1.490 đơn, CPO ~28,2; TỰ nhận ra 1.851 (ETS) và kịch bản (spend_reg) là 2 mô hình khác nhau nên so cùng mô hình (tự tính mức hiện tại 3.450/ngày ra ~1.680 đơn từ hệ số 0,87); phân tích biên: bỏ ~6.200 USD mất ~190 đơn = ~33 USD/đơn so với ~37 USD đóng góp mỗi đơn (AOV 54,6 × 0,682) → CM chỉ chênh ~900, nhỏ hơn sai số. Kiểm lại số: khớp.
  Thiếu: không nhắc hệ số spend là TƯƠNG QUAN 8 tuần, chưa phải nhân quả (phân tích biên dựa hẳn vào nó). "Gần Black Friday ads thường hiệu quả hơn" là kiến thức chung, dữ liệu chưa có.
- [x] 13/11: câu (4) spend 10.000/ngày: tool TỪ CHỐI đúng (322–4.175 đã thấy), Claude nói rõ là từ chối. NHƯNG rồi tự ngoại suy bằng hệ số nhớ từ câu (3) ra ~4.200 đơn, CM ~16.000 ("mức trần lạc quan") — đúng thứ tool cố ý không đưa. Phần lý do tốt (bão hoà, học lại, biên mỏng 37 USD, sức in POD) và đề xuất tăng từng bậc + theo dõi CPO bằng anomaly_check. Sửa: ToolError nói rõ KHÔNG tự ngoại suy, gợi ý kịch bản ở spend_max + tăng từng bậc; test kiểm. PASS.
- [x] 13/11: đo sai số TỔNG 14 ngày (Claude lấy WAPE ngày 23% làm sai số tổng). backtest `total_table` (TB |lệch|, bias, p80, tệ nhất theo mô hình); publish ghi thêm backtest_total_p80_pct, backtest_total_bias_pct vào 2 bảng; tool trả total_14d_range = tổng × (1 ± p80) cho cả ETS và kịch bản spend. metrics.yml thêm bẫy. 14 bộ test PASS.
- [x] Huy Anh: `python -m forecast.backtest` (xem bảng "Tổng 14 ngày") → `python -m forecast.publish` (ghi cột mới) → `python -m pipelines.dbt parse` → `python checks/check_mcp_sql.py` (21/21; PHẢI sau publish vì SQL đọc cột mới). Kèm output nạp dữ liệu sáng nay.
- [x] 13/11 sáng (đọc logs, không gọi API): pipelines.run 08:07 OK (Shopify 20 lần gọi 1%, orders 11.471; Meta 11 lần 2%; Klaviyo 96 lần 0%; check_raw OK). Reconcile 5–11/11: Shopify 802 = 802 ✓, Klaviyo 802 = 802 ✓, Meta 24.124,43 vs 24.124,28 ✓. dbt build PASS=152, WARN=2, ERROR=0.
  WARN MỚI: ad_type_chua_gan = 2 (campaign type mới chưa có trong seed). Huy Anh chạy checks/sql/check_type_moi.sql để biết type nào.
- [x] 13/11: publish mốc 11/11 (~1.851 đơn, k_ets 1,42, k_spend 1,3, hệ số 0,87); dbt parse OK; dry run 21/21 ✓.
- [x] Huy Anh chạy backtest (13/11, 256 ngày, mốc 15/7–28/10). ETS 14 ngày WAPE 23,2 (+16,2% so với naive), spend_reg 20,2. TỔNG 14 ngày: ETS TB |lệch| 18,3%, p80 32,6%, tệ nhất 69,9%; spend_reg TB 14,6%, p80 20,8%. → sai số tổng 14 ngày ở p80 (±33%) LỚN HƠN WAPE ngày 23% mà Claude dùng hôm nay: khoảng Claude nói hẹp hơn thật. Tool giờ đưa ±32,6%. Phủ ETS ngoài mẫu 73,8% (k 1,42).

### Review phần B (13/11): XONG
Đủ 5 tiêu chí: test máy (test_forecast 7 ca + chỉnh khoảng, test_forecast_publish, test MCP 7g); backtest cuốn chiếu không nhìn trước (ETS thắng naive ~16–17% ở 14 ngày; spend_hold thử và bỏ); kiểm định độ phủ ngoài mẫu (~70–74%, ghi rõ); dry run 21/21; thử thật 4/4 câu.
Sửa trong lúc làm: khoảng ETS chạy 2 lần ra 2 số (cố định seed); so số nạp dở với dự báo; tự cộng lo/hi; dùng WAPE ngày làm sai số tổng (thêm p80 lệch tổng); tự ngoại suy khi tool từ chối.
Giới hạn đã biết: chỉ 14 ngày; tổng tháng không đoán được khi còn > 14 ngày (lệch TB 24%, tệ nhất 59–63%); khoảng 80% thật ~70–74%; chưa có Q4; spend_reg là tương quan 8 tuần; không lưu bản dự báo cũ.
2 sửa cuối (không ngoại suy, total_14d_range) đã có test nhưng CHƯA thử lại trong phiên mới.

## MÔ HÌNH 8 XONG → ĐỦ 5 MÔ HÌNH (1, 2, 3, 5, 8)
- [x] 13/11 WARN ad_type_chua_gan: 2 campaign mới từ 11/11 (Catalog-PDP_Youth Hoodie_Theme $83,42; Catalog-Collection_Ceramic Ornament_Theme $82,42). Thêm seed Ceramic Ornament → Ornament (dòng con RCO đã có).
- [x] Huy Anh build sau seed Ceramic: còn 1 dòng chưa gán (Youth Hoodie) ✓. Câu 2: 92 mẫu "Youth Performance Hoodie" thuộc Hoodie / Performance Hoodie (đang bán cả 92) + 1 mẫu cũ đã ẩn. Thêm seed Youth Hoodie → Hoodie.
- [x] Huy Anh build `--select campaign_types+` (13/11): PASS=34, WARN=1, ERROR=0. ad_type_chua_gan = 0 ✓; WARN còn lại là 51 dòng ad đã xoá (như cũ).
- [x] 13/11: gộp vào `pipelines.run` (Huy Anh chọn): sau check_raw thêm bước `dbt` (pipelines.dbt build) rồi `forecast` (forecast.publish); bỏ được bằng `--skip dbt forecast`; log runs.jsonl ghi dòng "Done. PASS=" và "Mốc ...". Reconcile vẫn chạy riêng. test_run PASS.
  Nhịp mới mỗi sáng: `python -m pipelines.run` → `python checks/reconcile.py`.
- [x] 13/11 khoá chỉ đọc cho MCP (dòng 304, 399): `pipelines/bq.py` thêm `mcp_client()` (đọc MCP_CREDENTIALS; chưa có thì dùng khoá pipeline + cảnh báo stderr); server.py và check_mcp_sql.py dùng mcp_client; `checks/check_mcp_key.py` kiểm thật (đọc được gold, KHÔNG đọc raw/pii, KHÔNG tạo được bảng); hướng dẫn docs/cai-dat-bigquery.md mục 8 (datae-mcp: Job User cấp project + Data Viewer riêng dataset gold). Khác brief: chỉ gold, không silver (silver là view đọc raw). Test 8b PASS, 14 bộ test PASS.
- [x] Huy Anh tạo khoá datae-mcp (13/11). Lần đầu dòng .env chép nhầm dạng output của script ('TÊN': 'giá trị'); thêm `checks/check_env_names.py` (in tên biến, chỉ in giá trị của biến không bí mật) để soát. check_mcp_key: 5/5 ✓ (đọc gold; raw, pii 403; tạo bảng 403).
- [x] Huy Anh (13/11): check_bigquery OK bằng datae-pipeline (4 dataset); check_mcp_sql 21/21 bằng khoá datae-mcp.
- [x] Phiên mới (13/11) hỏi "hôm qua có gì lạ" bằng khoá datae-mcp: CHẠY, ra số. 11/11 (Veterans Day) gross_sales $7.858 vs kỳ vọng $5.148 (+53%, để ý, score 4,9); đơn 124 vs ~99, spend như thường, CPO $29 vs $33,9, MER 2,18. Claude tự soát product_performance (Long Sleeve 100 vs 63 cái, Cardigan 22 vs 0, Hoodie $707 vs $217) và email (4 campaign Veterans Day, Klaviyo gán 8 đơn ~$500). Đúng kiểu ngày lễ mà lịch sự kiện cần ghi. Hơi mạnh: "tăng chủ yếu do mua tự nhiên + ads ngày lễ" là suy luận.
- [x] 13/11 lịch sự kiện (Huy Anh chọn: ghi chú + bỏ khỏi mốc): seed `events.csv` 18 ngày (lễ Mỹ, BFCM, ngày tặng quà 2/2026–1/2027; thứ đã kiểm), gold `dim_event` (MCP đọc được); mart_anomaly_daily thêm cột event, ngày sự kiện không vào level_7d / hệ số thứ / TB 28 ngày (vars anomaly_level_min_days 5, min_base_weeks 6, rare_min_days 24); test anomaly_hop_ly thêm event_lech; anomaly_check trả event + ghi chú; forecast_orders trả events_in_window + cảnh báo BFCM; metrics.yml sửa bẫy. 14 bộ test PASS.
- [x] Huy Anh `python -m pipelines.dbt build` → chạy checks/sql/check_events.sql (3 câu) → `python checks/check_mcp_sql.py` (22/22).
- [ ] Hỏi anh Quang: ngày sale riêng của shop, lịch gửi campaign, hạn giao trước Giáng sinh (POD + hãng ship) để thêm vào events.csv.
- [x] Huy Anh build + check_events (13/11): câu 1 thấy 11/11 Veterans Day gross_sales "để ý", 21/6 Father's Day email_orders "để ý" ✓; 5/4 Easter cancel/refunds "(không tính được)" (trước 3/5 chưa có expected đơn, như cũ). Câu 3: 8–14/9 level_7d bỏ Labor Day ✓ (n_le_trong_7_ngay = 1).
  NHƯNG câu 2: 232 ngày (trước 227), có báo 33 (14,2%, trước 26 = 11,5%), cần xử lý 7 (trước 6). Báo động TĂNG, ngược kỳ vọng. Nghi: hạ ngưỡng số mốc (5/6/24) cho chấm thêm ngày nhưng mốc ít điểm → MAD nhiễu hơn. Viết câu 4 chia báo động theo nhóm (ngày sự kiện / mốc thiếu / sau sự kiện / thường).
- [x] Huy Anh câu 4 (13/11): báo động mới dồn vào ngày ĐẦU 4–5/2026 (4/25 cpo, 5/6 mer, 5/9 new_share, 5/13–14, 5/20…) và nhóm "mốc thiếu" (n_base 6–7, 27): hạ ngưỡng số mốc làm chấm thêm các ngày lúc shop rất nhỏ (mer trước bắt đầu 26/5, giờ 6/5). Đúng nghi vấn.
- [x] Sửa tận gốc: bỏ 3 vars hạ ngưỡng; điều kiện chấm giữ như cũ (đủ 7 ngày lịch có số, đủ 8 ngày cùng thứ / 28 ngày THƯỜNG); gặp ngày sự kiện thì LÙI XA thêm (tối đa 12 tuần / 42 ngày) và kiểm không hụt ngày lịch nào. Test n_base về đúng 8 / 28.
- [x] Huy Anh build lại (13/11): 228 ngày (227 + ngày 11/11 mới), có báo 25 = 11,0% (trước lịch 11,5%), cần xử lý 6; câu 4 không còn "mốc thiếu", mọi n_base = 8/28; báo động ngày sự kiện: Father's Day email, Veterans Day gross; dry run 22/22 ✓. LỊCH SỰ KIỆN XONG.

## Tuần 4: MCP cho AI + bàn giao (đối chiếu 13/11, chờ Huy Anh chọn hướng)
Brief: key chỉ đọc silver + gold nối MCP Toolbox; mô tả bảng/cột trong dbt; Claude trả đúng 5 câu mẫu; README + demo 30 phút (anh Quang tự gõ câu hỏi).

Đã có / còn thiếu:
- Key: datae-mcp chỉ đọc GOLD (5/5 check). Thiếu silver: view silver đọc raw, key phải đọc được raw hoặc silver là authorized view.
- MCP: server Python riêng 15 tool viết sẵn SQL, CHƯA dùng MCP Toolbox, chưa có tool tự viết SQL (Text-to-SQL).
- Mô tả dbt: _marts.yml có nhiều cột; chưa đo phần trăm bảng/cột có mô tả (đo được từ manifest.json, không cần khoá).
- 5 câu mẫu:
  - [x] 1. MER + CM ước 7 ngày (ngày Phoenix): daily_performance / performance_summary, có vẻ đủ, chưa thử thật.
  - [x] 2. Top 10 species theo Rev 28 ngày so 28 ngày trước: CHƯA có tool gom theo species (dim_product có species).
  - [x] 3. Tỉ lệ mua lần 2 trong 60 ngày theo type của đơn đầu: CHƯA có.
  - [x] 4. ROAS theo type tuần trước (CN–T7): type_performance, có vẻ đủ, chưa thử thật.
  - [x] 5. Doanh thu email (Klaviyo attributed) so tổng Rev theo tuần: email_performance + performance_summary, phải tự gom tuần, chưa thử.
- [x] README bàn giao (gom mục "khác brief") + kịch bản demo 30 phút. (13/11: B8)

Huy Anh chốt 13/11: (1) GIỮ server 15 tool + THÊM MCP Toolbox (Claude tự viết SQL, khoá chỉ đọc); (2) silver đọc qua AUTHORIZED DATASET (silver được đọc raw, khoá vẫn 403 ở raw/pii); (3) câu 3 có bảng gold riêng, câu 2 và 5 để Claude tự viết SQL.

Kế hoạch tuần 4 (chờ duyệt, làm từng bước, chứng minh xong mới sang bước sau):
- [x] B1. Đo độ phủ mô tả dbt từ manifest.json (không cần khoá): bảng/cột nào thiếu mô tả ở silver + gold.
  - [x] checks/check_docs.py: đọc manifest (mô tả đã khai) + catalog (cột thật), không gọi BigQuery.
  - [x] Lần đo đầu (13/11, catalog cũ 11/11): bảng có mô tả 32/33 (thiếu int_order_refunds), cột 122/352 = 35%. Gold cột thưa: fct_ad_day 3/24, fct_lines 4/26, fct_orders 4/21, email_daily 1/11, dim_variant 3/13. Silver gần như trống.
  - [x] Huy Anh docs generate + check_docs (13/11, catalog mới): bảng 32/33, cột 125/402 = 31%. Hết báo nhầm fct_ad_day. Dry run MCP 22/22. B1 XONG.
  - Ghi chú: gold.forecast_daily / forecast_spend_model không phải model dbt (publish.py ghi), mô tả nằm ở _sources.yml; B2 xử lý riêng.
- [x] B2. Viết mô tả còn thiếu (_staging.yml, _marts.yml), ghi rõ đơn vị, ngày Phoenix, bẫy. Bật persist_docs để mô tả lên BigQuery (Toolbox đọc được). Huy Anh build.
  - [x] Thêm mô tả ~285 cột (script chèn văn bản, giữ test/ghi chú): _marts.yml, _staging.yml (thêm khối int_order_refunds), _seeds.yml. Đơn vị USD, ngày Phoenix/UTC, bẫy (reach không cộng, meta_* tự nhận, email '(không gán)' không phải doanh thu email, product_line = 'product type').
  - [x] dbt_project.yml: +persist_docs {relation, columns} cho models và seeds.
  - [x] Tự kiểm (đọc yml so catalog, không gọi BigQuery): 402/402 cột có mô tả, không khai sai tên cột, YAML hợp lệ.
  - [x] Huy Anh build (13/11): PASS=191 WARN=1 (51 ad đã xoá, như cũ) ERROR=0. check_docs: .yml 33/33 bảng, 402/402 cột.
  - [x] check_docs thêm dòng đếm mô tả THẬT trên BigQuery (comment trong catalog). Catalog 02:36 UTC (trước build): 0/33, 0/402, đúng mốc trước.
  - [x] Huy Anh docs generate sau build (13/11): Trên BigQuery 33/33 bảng, 402/402 cột. persist_docs chạy. B2 XONG.
  - Để lại: 2 bảng forecast_* do publish.py ghi, chưa có mô tả cột trên BigQuery (Toolbox thấy cột trơn). Câu dự báo đã có tool forecast_orders nên chưa làm.
- [x] B3. Bảng gold câu 3 (1 dòng = 1 khách: type đơn đầu, ngày đơn 2, đủ 60 ngày chưa) + test dbt + câu kiểm số. Chốt cách tính đơn đầu nhiều type trước khi viết.
  - [x] Huy Anh chốt: đơn đầu nhiều type → type doanh thu dòng lớn nhất (+ is_multi_type); bỏ đơn huỷ cả đơn đầu và đơn 2; mua lần 2 = ngày khác, 1–60 ngày (đơn cùng ngày ghi has_same_day_extra).
  - [x] mart_repeat_60d.sql + mô tả _marts.yml + tests/repeat_hop_ly.sql (đơn 2 khác ngày, eligible ↔ null, repeat 1–60, cùng tập khách với mart_rfm). is_eligible: đơn đầu ≤ (ngày đặt mới nhất − 1) − 60.
  - [x] Huy Anh check_tuan4_b3 (13/11): câu 1 cộng 5.308 khách đủ 60 ngày, 685 mua lần 2 = câu 2 tính độc lập 5.308 / 685 ✓ (tổng 12,9%). Long Sleeve 13,5% (633/4.689), Short Sleeve 10,3%, Hoodie 6,2% (12/194), Zip Hoodie 4,0%. Phone Case, Ornament, Blanket chưa có khách đủ 60 ngày (type mới). Câu 3: dim 9.449 khách, mart 9.439 (10 khách chỉ có đơn huỷ), 178 khách có đơn cùng ngày. B3 XONG.
  - Bẫy cho demo: Hoodie thấp có thể do khách hoodie mới (mùa thu), không hẳn ít quay lại; tỉ lệ so giữa type lệch thời điểm.
- [x] B4. Quyền silver: hướng dẫn authorized dataset (silver → raw) + cấp datae-mcp Data Viewer trên silver; sửa check_mcp_key thêm đọc 1 view silver. Huy Anh bấm + chạy check.
  - [x] docs/cai-dat-bigquery.md mục 9 (a: raw → Authorize Datasets → silver; b: datae-mcp Data Viewer trên silver). Mục 8b sửa lời cũ.
  - [x] check_mcp_key: thêm đọc silver.stg_orders (view → raw) và silver.product_lines (seed); 7 mục.
  - [x] Huy Anh làm mục 9 + check_mcp_key (13/11): 7/7 ✓ (đọc gold, silver view + seed; 403 raw, pii, tạo bảng). B4 XONG.
- [x] B5. MCP Toolbox: cài (thử exe; bị chặn thì npx), tools.yaml chỉ bigquery-execute-sql/list/get-table-info, dataset silver + gold, khoá datae-mcp; nối vào .mcp.json cạnh server datae.
  - [x] Tra docs mcp-toolbox (repo đổi tên googleapis/mcp-toolbox): cấu hình nhiều tài liệu `kind:`, cờ `--config`, source có readOnly / writeMode blocked / allowedDatasets (dry run chặn dataset ngoài danh sách) / maximumBytesBilled. Chọn v1.16.0 (có SHA256 công bố; v1.17.0 ra 13/11, quá mới).
  - [x] mcp_toolbox/tools.yaml: source datae-bq (readOnly, blocked, allowedDatasets silver+gold, 200 MB, 200 dòng) + 3 tool execute_sql, list_table_ids, get_table_info (mô tả có quy tắc ngày Phoenix, MER từ tổng, ngày dở).
  - [x] Huy Anh cho tải (13/11): bin/toolbox.exe từ storage.googleapis.com/mcp-toolbox-for-databases/v1.16.0, so SHA256 326c9783…7e7f; bin/ vào .gitignore.
  - [x] Tải xong 295 MB, SHA256 KHỚP 326c9783…7e7f. `toolbox.exe --version` = 1.16.0, Application Control KHÔNG chặn.
  - [x] mcp_toolbox/run.py: đọc MCP_CREDENTIALS từ .env, TỪ CHỐI nếu thiếu hoặc không phải datae-mcp (không dùng tạm khoá pipeline như server datae), đặt GOOGLE_APPLICATION_CREDENTIALS + BIGQUERY_PROJECT/LOCATION rồi chạy toolbox --stdio.
  - [x] .mcp.json thêm server datae-sql (python -m mcp_toolbox.run). checks/check_toolbox.py: 6 mục (đọc gold, silver; get_table_info có mô tả; từ chối raw, pii, create table).
  - [x] Huy Anh check_toolbox (13/11): 6/6 ✓. gold 742 dòng, silver.stg_orders 11.471 (view → raw qua authorized dataset), get_table_info trả mô tả bảng/cột; raw, pii bị Toolbox chặn ("access to dataset ... is not allowed"); create table bị IAM chặn (403 tables.create) ngay ở dry run. B5 XONG (còn duyệt server datae-sql ở phiên mới, làm cùng B7).
- [x] B6. SQL đáp án 5 câu (checks/sql/check_tuan4_dap_an.sql), Huy Anh chạy lấy số đúng.
  - [x] Quy ước: ngày trọn cuối = max(order_date) − 1; tỉ số từ tổng; tuần CN → T7. Câu 1 mart_daily_kpi 7 ngày + tổng; câu 2 line_revenue theo dim_product.species, 28 vs 28 ngày trước; câu 3 mart_repeat_60d; câu 4 mart_type_day tuần trọn gần nhất; câu 5 email_daily placed_value (campaign + flow) vs daily_performance.rev, 8 tuần.
  - [x] Lần chạy 1 (13/11): câu 2, 3 chạy được. Câu 4, 5 lỗi EXTRACT(... FROM STRUCT): CTE `d` có cột cũng tên `d`, BigQuery hiểu `d` là cả dòng → đổi cột thành ngay_tron ở cả 5 câu (lần thay đầu làm hỏng tên bảng dim_product/daily_performance, đã sửa, kiểm lại danh sách bảng). Câu 1 lỗi 'th' tại [1:1] = chép thiếu đầu câu (dòng ghi chú bị cắt), không phải lỗi SQL.
  - [x] Câu 2: '(không có species)' 88.796,94 USD 28 ngày (+269% so 28 ngày trước 24.047,68) lớn hơn cả 10 loài cộng lại: phần lớn doanh thu Q4 (hoodie, mẫu mới) không có tag species. Top loài: deer 11.972,65 (−0,3%), bear 6.503,20 (+33,3%), redfish 6.471,77 (+47,9%), deepsea, walleye, bass, musky, trout, mallardduck, alligator. Claude phải nói rõ bẫy này.
  - [x] Câu 3: như check_tuan4_b3 (5.308 / 685).
  - [x] Lần chạy 2 (13/11 VN, ngày trọn cuối 11/11 Phoenix). ĐÁP ÁN (chỉ đúng tới khi pipeline nạp ngày 12/11):
    - Câu 1 (5–11/11): rev 44.246,90, spend 24.124,28, MER 1,83, CM ước 6.052,10. Từng ngày MER 1,34 (5/11, CM −294,43) → 2,18 (11/11, CM 1.758,07). Tự cộng lại khớp.
    - Câu 2: xem lần chạy 1 (deer, bear, redfish…; '(không có species)' 88.796,94).
    - Câu 3: tổng 12,9%; Long Sleeve 13,5%, Short Sleeve 10,3%, Hoodie 6,2%, Zip Hoodie 4,0%.
    - Câu 4 (1–7/11): Long Sleeve ROAS 1,58 (17.601 / 11.175), Phone Case 1,51, Ornament 1,80, Hoodie 3,54, AirPods Case 0,61, Short Sleeve 6,11, Fleece Blanket 0,84, Cardigan 0 (spend 138,39, chưa có đơn), Quilt 2,86, Can Cooler 1,06, '(không theo type)' spend 96,91. '(không rõ)' rev 54,43 = khoản lệch lineitem 54,43 đã biết.
    - Câu 5 (8 tuần 13/9 → 1/11): email 9,3% → 15,0% (20/9) → 5,7% (1/11); tuần 1/11 rev 44.319,85, email 2.525,80 (flow 2.290,88, campaign 234,92). Tỉ trọng email giảm vì rev tăng gấp 3 nhờ ads, email gần như đứng.
  B6 XONG.
- [x] B7. Phiên Claude mới hỏi 5 câu, so với đáp án; sai thì sửa mô tả/tool, không sửa câu hỏi.
  - [x] Lần thử 1 (13/11, phiên "DataE server testing và validation"): số KHỚP cả 5 câu, và đọc transcript thấy số đến từ truy vấn thật: câu 1 performance_summary + daily_performance, câu 4 type_performance (server datae); câu 2, 3, 5 execute_sql tự viết (datae-sql), sau khi get_table_info fct_lines, dim_product, mart_repeat_60d, email_daily. SQL tự tìm ngày trọn = max − 1 và tuần CN → T7, đúng quy ước.
    NHƯNG chưa phải lần chạy mù: phiên được dán nguyên tin nhắn hướng dẫn của mình nên Grep tasks/todo.md (có đáp án) trước, và câu hỏi gõ là tiêu đề bảng của mình kèm ngày ("MER, CM ước 7 ngày (5–11/11)"), không phải câu brief. Phiên đó tự nói rõ điều này.
  - [x] Lần thử 2 MÙ (13/11, phiên "MER và CM ước 7 ngày qua theo ngày Phoenix"): chỉ gõ nguyên văn câu brief (câu 2+3 dán chung 1 tin). Transcript: 0 lần Read/Grep/Bash, không đụng todo hay file đáp án; tool: today_phoenix, performance_summary, daily_performance, type_performance (datae) + list_table_ids, get_table_info ×4, execute_sql ×4 (datae-sql).
    - Câu 1 khớp (tự tìm 5–11/11 qua today_phoenix; thêm mốc hoà vốn 1,47, cảnh báo giá vốn tạm). Câu 2 khớp cả 10 loài + nêu bẫy 54% không tag. Câu 3 khớp (nêu bẫy kho từ 11/2024). Câu 4 khớp 8 type chính, bỏ sót 3 dòng nhỏ (Quilt 2,86, Can Cooler 1,06, '(không theo type)' 96,91 spend); có nêu bẫy ROAS gán cả đơn tự nhiên. Câu 5 khớp 8 tuần (tuần 13/9 ghi 9,4% thay 9,3%: chia số đã làm tròn), thêm tuần 8/11 dở có đánh dấu *.
    - Không sửa mô tả/tool: lệch chỉ là làm tròn và lược dòng nhỏ. B7 XONG.
- [~] B8. README bàn giao (cài đặt, chạy hằng ngày, mục "khác brief") + kịch bản demo 30 phút.
  - [x] README.md viết lại: kho gồm gì (luồng, 4 dataset), hỏi số qua 2 server + an toàn, chạy hằng ngày, cài máy mới, bảng kiểm, 9 dòng "khác brief" có lý do, việc chờ anh Quang, thư mục; giữ cổng khớp số tuần 3 làm phụ lục. Số model/test lấy từ manifest (30 model, 4 seed, 165 test).
  - [x] docs/demo-ban-giao.md: chuẩn bị sáng hôm demo (chạy lại đáp án vì số đổi mỗi ngày, phiên mới, đóng todo), kịch bản 0–3 / 3–7 / 7–22 (anh tự gõ 5 câu, bẫy nói sau) / 22–26 (câu tự do + thử an toàn) / 26–30 (bàn giao).
  - [x] Phát hiện khi viết: khoá chỉ đọc chỉ chặn đường MCP; Claude Code còn shell, máy có khoá pipeline (ghi, đọc pii) trong .env thì Claude vẫn có thể đề nghị dùng (có hỏi trước). Ghi rõ ở README mục 2 và kịch bản demo, không nói quá là "không thể".
  - [x] Kiểm: 20 file/lệnh nhắc trong 2 tài liệu đều có; 14 bộ test Python PASS.
  - [ ] Huy Anh đọc README + kịch bản, sửa giọng nếu cần; chốt ngày demo với anh Quang.

## Dashboard tổng quan KPI (13/11, ngoài brief, Huy Anh duyệt, cho tự chạy kiểm)
Huy Anh chốt: web app chạy trên máy; chưa có Anthropic API key nên CHƯA có ô chat, hỏi đáp vẫn ở Claude Code; chỉ phần tổng quan KPI.

Kế hoạch:
- [x] D1. `dashboard/app.py` (Streamlit 1.66 + Altair 6.3, đã cài sẵn). Đọc `gold.mart_daily_kpi` bằng khoá CHỈ ĐỌC datae-mcp (từ chối nếu thiếu, như mcp_toolbox/run.py), 1 câu SQL cho kỳ chọn + kỳ trước, cache 10 phút, giới hạn 50 MB/câu.
- [x] D2. Bộ lọc: mặc định 7 ngày trọn cuối (bỏ ngày mới nhất đang dở); chọn nhanh 7 / 14 / 28 ngày, tháng này; so kỳ trước cùng độ dài.
- [x] D3. 7 ô KPI brief (Rev, đơn, AOV, spend, MER, CPO, CM ước) kèm % so kỳ trước; MER, AOV, CPO tính từ TỔNG.
- [x] D4. 3 biểu đồ theo ngày: Rev và spend; MER với đường hoà vốn 1/(1 − 28% − 3,8%) ≈ 1,47; CM ước (âm/dương). Bảng số từng ngày bên dưới. Ghi chú: giá vốn tạm, ngày dở.
- [x] D5. Giao diện Midnight Forge (DESIGN.md): .streamlit/config.toml + CSS, chữ Plus Jakarta Sans / JetBrains Mono.
- [x] D6. Kiểm: chạy trên localhost (dùng khoá datae-mcp, cần Huy Anh đồng ý), số 5–11/11 phải khớp đáp án câu 1 (rev 44.246,90, MER 1,83, CM 6.052,10); xem trên máy tính và điện thoại; test Python cho phần tính tổng.
- Review dashboard (13/11):
  - `dashboard/kpi.py` (tính tổng, kỳ, ngày trọn, hoà vốn đọc từ dbt_project.yml) + `dashboard/app.py` (Streamlit) + `.streamlit/config.toml` + launch.json "dashboard". tests/test_dashboard.py 5/5 (dùng số thật 5–11/11; kiểm MER từ tổng khác trung bình từng ngày, thiếu spend thì MER/CPO/CM trống, ngày dở bị loại).
  - Màu biểu đồ qua validate_palette.js (dark, nền #111A2E): Rev #1FA884, Spend #7B83F6 PASS. Cặp xanh/đỏ cho CM lãi/lỗ FAIL mù màu (ΔE 2,0) → CM 1 màu, dấu bằng vị trí so vạch 0.
  - Chạy thật trên localhost bằng khoá datae-mcp: 7 ngày 5–11/11 ra Rev 44.247, 802 đơn, AOV 55,17, spend 24.124, MER 1,83, CPO 30,08, CM 6.052 = đáp án câu 1. 28 ngày 15/10–11/11: Rev 176.704, MER 1,94, CM 29.464 (tự cộng lại khớp). Điện thoại 375px không cuộn ngang.
  - Lỗi gặp và sửa: tickCount=None (Altair cần alt.Undefined); selection nearest trên mark_bar làm Vega lỗi "_marks" → bỏ ở cột; thứ tiếng Anh → T2…CN; AOV/CPO làm tròn mất số lẻ → 2 chữ số; dòng so kỳ trước dùng mono → đổi Plus Jakarta (DESIGN: mono chỉ cho terminal).
  - Chưa có: ô chat Claude (chờ Anthropic API key); chọn ngày tuỳ ý (bỏ vì date_input khoảng dễ lỗi, dùng 4 nút chọn nhanh).
  - Chạy: `python -m streamlit run dashboard/app.py` → http://localhost:8501

## Test MCP (13/11 chiều)
- [x] tests/test_mcp_server.py PASS (offline, 15 tool).
- [x] Gọi thật trong phiên đang mở: today_phoenix (12/11, trọn 11/11), performance_summary 5–11/11 = đáp án câu 1 (802 đơn, rev 44.246,90, MER 1,8341, CM 6.052,10).
- [x] (giải thích) anomaly_check trong phiên cũ trả bản CŨ (không cột event, ghi chú "Chưa có lịch sự kiện"): server MCP của phiên nạp lúc khởi động, trước khi sửa. Code server.py đã đúng (dòng 659, 725). Test thật phải ở phiên mới.
- [x] Phiên mới "Hôm qua có gì lạ không?" (13/11): transcript không đọc file, chỉ tool datae.
  - Câu 1: anomaly_check có event "Veterans Day" cho 11/11, gross_sales "để ý" (+53%, score 3,78); Claude tự gọi thêm email_performance, daily_performance, product_performance để giải thích (giỏ to hơn, 4 campaign Veterans Day). ĐẠT.
  - Câu 2: forecast_orders → tổng 1.851, khoảng 1.248–2.454 (total_14d_range, ±32,6%), không cộng lo/hi; nêu BFCM, pacing tháng chưa đoán (còn 19 ngày). ĐẠT.
  - Câu 3: 10.000 USD/ngày → ToolError, Claude không đưa số. ĐẠT. NHƯNG lời từ chối in khoảng "322–4,175" (spend_max 4.174,6 làm tròn lên) và gợi ý "kịch bản ở spend_max": Claude thử 4175 → bị từ chối, phải thử 4170.
  - [x] Sửa: in cận dưới làm tròn lên, cận trên làm tròn xuống, gợi ý ghi đúng số dùng được; `import math` lên đầu file. Test 7g thêm: spend_min 899,6 / max 3.800,4 → lời từ chối in "900–3,800", gọi 3800 và 900 đều chạy. 15 bộ test PASS. Cần phiên mới để server nạp bản sửa.
- [x] Huy Anh chạy (13/11 10:49): check_mcp_sql 22/22, check_mcp_key 7/7, check_toolbox 6/6. TEST MCP XONG.
- [x] Tập demo 13/11 (phiên mới, 5 câu): khớp đáp án cả 5. Câu 4 lặp lại lỗi lần thử mù: lược type nhỏ (Quilt, Can Cooler, '(không theo type)') và chỉ coi ROAS < 1 là lỗ (bỏ sót Can Cooler 1,06).
  - [x] Sửa type_performance: trả thêm breakeven_roas (1 / biên, đọc dbt vars = 1,47) và below_breakeven (type có spend, ROAS dưới ngưỡng); ghi chú dặn liệt kê ĐỦ mọi dòng (kèm số dòng). Test thêm Cardigan 0, Can Cooler 1,06, dòng spend 0 → below_breakeven = [Cardigan, Can Cooler]. docs/demo-ban-giao.md cập nhật bẫy câu 4.
  - [x] Phiên mới hỏi lại câu 4 (13/11): đủ 12 dòng (11 có spend + '(không rõ)'), gọi đúng 5 dòng lỗ gồm Can Cooler 1,06; tổng rev 41.214 / spend 24.098 / ROAS 1,71 khớp. Lệch: Claude tự cộng spend 5 dòng lỗ ~1.035 (thật 1.024,98).
  - [x] Sửa tiếp: tool trả sẵn below_breakeven_spend và total {rev, spend}, test kiểm số cộng. 15 bộ test PASS. Cần phiên mới để nạp.
  - Phát hiện của Claude đáng báo anh Quang: '(không theo type)' vẫn tiêu 96,91 USD tuần 1–7/11, tức còn campaign đặt tên kiểu cũ đang chạy (spend đó không chia được theo type).

## Review code 13/11 (agent đọc độc lập code sửa hôm nay)
- [x] type_performance: '(không theo type)' (rev 0 → roas 0, KHÔNG null như comment mart_type_day ghi) bị tính là type lỗ, nên below_breakeven_spend 1.024,98 hôm nay là SAI (đúng 928,07; 96,91 là spend chưa gán type). Sửa: loại dòng này, trả riêng untyped_spend; sửa comment mart_type_day.
- [x] type_performance so ROAS đã làm tròn (1,4655 in 1,47 lọt ngưỡng 1,4663) → so bằng rev / spend chưa làm tròn.
- [x] forecast_orders: spend quá THẤP vẫn khuyên "kịch bản ở mức cao nhất, tăng ngân sách" → gợi ý mức thấp nhất.
- [x] dashboard: kỳ trước thiếu ngày thì không so (tránh "▲ tốt hơn" giả); money(NaN) ra "– $" → "–"; kho trống thì báo rõ thay vì TypeError.
- Test thêm cho cả 4 (test_mcp_server 7g + type). 15 bộ test PASS. Chưa chạy lại dashboard trên trình duyệt (cổng 8501 Huy Anh đang dùng); py_compile OK.
- Để lại (nhỏ, có ghi): preset "Tháng này" theo tháng của ngày trọn cuối (pipeline dừng qua đầu tháng thì là tháng trước); đáp án câu 2 tính cả Tip/Shipping Protection vào '(không có species)'; đáp án câu 1 lệch nếu có ngày thiếu spend (hiện không có).
- Agent xác nhận đúng: mart_repeat_60d + test, mcp_toolbox/run.py, check_mcp_key, check_toolbox, check_docs, SQL đáp án câu 3–5.


## Dashboard thêm 4 tab (13/11, Huy Anh chọn cả 4, duyệt làm hết)
Giữ tab Tổng quan KPI; dùng chung bộ lọc khoảng ngày (trừ phần không theo ngày như RFM, ABC). Mỗi tab chỉ đọc bảng gold đã kiểm, khoá datae-mcp, ≤ 50 MB/câu, cache 10 phút. Tách code: dashboard/app.py (khung + bộ lọc) và dashboard/views/*.py (mỗi tab 1 file), dashboard/charts.py (kiểu biểu đồ chung).
- [x] T1. Quảng cáo & type: cột ngang ROAS theo type + vạch hoà vốn 1,47 + nhãn "đang lỗ" (cùng quy tắc type_performance: bỏ '(không theo type)', so số chưa làm tròn); top 10 campaign theo spend (spend, CTR, CPM, mua Meta tự nhận ghi rõ "tham khảo"); phễu Meta (hiển thị → click link → xem SP → giỏ → thanh toán → mua, Meta tự nhận).
- [x] T2. Sản phẩm: doanh thu dòng sản phẩm theo tuần (5 dòng lớn + "Khác"); ABC: số mẫu và % doanh thu theo nhóm A/B/C/D/Mới + top 15 mẫu; top 10 species kỳ chọn so kỳ trước (kèm % "(không có species)").
- [x] T3. Khách & email: đơn khách mới / khách cũ / không email theo tuần; mua lần 2 trong 60 ngày theo type đơn đầu; 9 nhóm RFM (số khách, % doanh thu); bảng cohort giữ khách (ô đậm nhạt theo %); doanh thu email (campaign, flow) và % Rev theo tuần.
- [x] T4. Cảnh báo & dự báo: bảng báo động 14 ngày gần nhất (mức, chỉ số, % lệch, sự kiện); 28 ngày đơn thật + 14 ngày dự báo với dải 80%, tổng 14 ngày + khoảng (p80 backtest).
- [x] T5. Màu: bảng categorical tối đa 6 màu chạy validate_palette.js (dark); tuần CN–T7; số kiểu Việt; tooltip mỗi biểu đồ.
- [x] T6. Kiểm: số mỗi tab so với đáp án đã có (câu 2–5, anomaly 11/11 Veterans Day, forecast 1.851 / 1.248–2.454); máy tính + điện thoại; console không lỗi; test Python cho phần tính mới.
- Review 4 tab (13/11):
  - Code: dashboard/data.py (mọi câu SQL, khoá datae-mcp, tham số, 50 MB, cache), charts.py (màu, số kiểu Việt, style), views/ads|products|customers|alerts.py, app.py thành 5 tab. kpi.py thêm weeks_window, roas_flags (cùng quy tắc MCP type_performance). test_dashboard 7/7, 15 bộ test PASS.
  - Màu: CAT 5 màu (teal, cam, tím, vàng, hồng) validate_palette PASS dark; 'Khác' xám; type lỗ màu critical + chữ "▼ đang lỗ" (không dựa vào màu).
  - So số (cổng 8502, khoá datae-mcp): species 28 ngày = đáp án câu 2 (deer 11.973 −0,3%, 54% = 88.797 không tag); dự báo 1.851, khoảng 1.248–2.454 = tool forecast_orders; báo động 11/11 Veterans Day gross_sales +53%; tab Tổng quan giữ nguyên số câu 1.
  - Lỗi gặp khi kiểm, đã sửa: trục ROAS kéo tới 327 (type spend ~0) → chặn trục 6, ghi "(vượt trục)"; phễu "111,84%" (Meta đếm riêng từng bước) → ghi "Meta đếm riêng"; Vega giấu xen kẽ nhãn trục dọc → labelOverlap False; khoảng dự báo lệch 1 đơn với tool (làm tròn) → làm tròn tổng trước; species "-0%" → 1 chữ số.
  - Bài học: Streamlit không nạp lại module con (views/*) khi rerun; sửa module thì khởi động lại server.
  - Chưa làm: email theo tuần chưa so tay từng tuần với đáp án câu 5 (cùng logic SQL); điện thoại: trang không cuộn ngang, bảng tự cuộn trong khung.
- [x] 13/11 Huy Anh: chuyển thanh tab sang cột dọc bên trái. Cột trái (st.sidebar): logo DataE, menu 5 trang (st.radio, ẩn chấm tròn, mục chọn nền teal-deep), khoảng ngày, ghi chú ngày Phoenix. Chỉ dựng trang đang chọn (không chạy SQL trang khác). Tiêu đề trang = tên trang, nhãn trên = khoảng ngày.
  - Lỗi gặp khi kiểm, đã sửa: CSS ẩn chấm tròn theo cấu trúc Streamlit 1.66 (label[data-testid=stRadioOption], data-selected); rule font [class*="st-"] đè font icon → nút thu cột trái in chữ "keyboard_double_arrow_left" (bỏ rule đó, đặt font cho .stMarkdown * và icon Material riêng); cột trái cuộn ngang (box-sizing); điện thoại: nút mở cột trái đè nhãn đầu trang (padding-top 56px).
  - Kiểm (cổng 8502): máy tính cột trái 300px, nội dung bên phải, chuyển trang đúng, 0 lỗi; điện thoại cột trái tự thu, không cuộn ngang. 15 bộ test PASS.

## Nạp 16/11
- [x] pipelines.run 08:04 VN (18:04 Phoenix 15/11): shopify 250 s, meta 192 s, klaviyo 119 s, check_raw, dbt PASS=198 WARN=1 (51 ad xoá) ERROR=0, forecast mốc 14/11 (ETS 14 ngày ~1.817, k 1,29). Log: logs/run_2026-11-16.txt.
- [x] reconcile 8–14/11: Shopify 874 = 874, Meta 24.448,07 vs 24.447,38 (≤ 1 USD/ngày), Klaviyo 874 = 874.
- Tin: tuần 8–14/11 874 đơn (+7%), rev 48.379,69 (+9%), MER 1,98, CPO 27,97, CM ước 8.547,57 (+39%). 13/11 tốt nhất (151 đơn, MER 2,50, để ý). 12/11 kém (MER 1,37, dưới hoà vốn). Type dưới hoà vốn: Phone Case 1,47 (sát, spend 6.652), AirPods Case 0,50 (spend 1.335). Cardigan đổi chiều: 4,38 (rev 4.352). Spend chưa gán type giảm còn 29,63. Dự báo 15–28/11: 1.817 đơn (1.246–2.388), có Thanksgiving, Black Friday, Small Business Saturday trong khung.
- [ ] Theo dõi: 14/11 email_orders = 0 dù flow vẫn gửi; xem lại sau lần nạp tới (Klaviyo gán trễ?).
- [ ] (nhỏ) email_performance trả cả message received = 0 (22 dòng campaign rỗng), nên lọc bỏ cho gọn.
- [x] Huy Anh chạy tay pipelines.run + reconcile (16/11): OK, khớp nguồn. Kho vẫn tới 14/11 Phoenix (Phoenix đang 15/11). Spend 14/11 Meta chỉnh 3.167,02 → 3.167,18. 14/11 email_orders vẫn 0 → xem lại sau lần nạp 17/11.

## Dashboard React + backend (16/11, Huy Anh duyệt, cho tải)
Huy Anh chốt: chỉ chạy trên máy mình; backend tự bật khi đăng nhập Windows (lối tắt trong thư mục Startup, Huy Anh tự tạo); nạp dữ liệu xong thì trang tự có số mới, không gõ lệnh. Mô hình giữ nguyên trong dbt gold, backend chỉ ĐỌC kết quả.

Kiến trúc:
- Backend `webapp/api/` (FastAPI + uvicorn, Python như phần còn lại): dùng lại khoá chỉ đọc datae-mcp, các câu SQL của `dashboard/data.py` và phép tính của `dashboard/kpi.py` (1 chỗ định nghĩa, không chép). Mỗi trang 1 endpoint JSON (`/api/overview`, `/api/ads`, `/api/products`, `/api/customers`, `/api/alerts`), tham số khoảng ngày. ≤ 50 MB mỗi câu.
- Tự có số mới: `/api/version` đọc thời điểm sửa cuối của các bảng gold (metadata BigQuery, không tốn truy vấn). Cache trong backend theo version đó; trang React hỏi version mỗi 60 giây, đổi thì tải lại số.
- Frontend `webapp/web/` (React 18 + Vite 7, vì Vite 8 bị Application Control chặn; biểu đồ Recharts): 5 trang như bản Streamlit, menu dọc bên trái, Midnight Forge, số kiểu Việt. Build ra file tĩnh, backend phục vụ luôn ở cùng 1 cổng `http://localhost:8600`.
- Tự bật: `webapp/start.vbs` chạy backend ẩn (không hiện cửa sổ), ghi log ra `logs/webapp.log`; hướng dẫn tạo lối tắt trong `shell:startup`.
- Giữ bản Streamlit tới khi bản React kiểm xong, rồi hỏi có xoá không.

Các bước (xong bước nào kiểm bước đó):
- [x] W1. Cài FastAPI + uvicorn (pip) và gói npm (react, vite 7, recharts) — cần Huy Anh cho tải.
- [x] W2. Backend: endpoint + cache theo version + test (dữ liệu giả, không dùng khoá).
- [x] W3. Frontend: khung (menu trái, bộ lọc ngày), trang Tổng quan, so số với bản Streamlit.
- [x] W4. 4 trang còn lại, so số từng trang với bản Streamlit / tool MCP.
- [ ] W5. Tự có số mới: chạy pipelines.run (Huy Anh) → trang tự đổi trong ≤ 60 giây.
- [x] W6. start.vbs + hướng dẫn Startup; khởi động lại máy vẫn mở được trang. README cập nhật.
- Review React + backend (16/11):
  - W1: fastapi 0.115.14, uvicorn 0.32.1 (pip --user); react 18.3.1, vite 7.1.12, @vitejs/plugin-react 5.0.4, recharts 2.15.4 (npm, 105 gói). esbuild chạy được (Application Control không chặn).
  - W2: SQL tách ra dashboard/queries.py (Streamlit data.py chỉ còn bọc cache). webapp/api/pages.py (số từng trang, dùng kpi.py), main.py (FastAPI: /api/meta, /api/page/{tên}?preset=, phục vụ dist/). Phiên bản = max lần sửa 15 bảng gold (get_table song song: 15 s → ~1 s). Cache theo (trang, preset, phiên bản); đổi phiên bản thì tính sẵn 5 trang song song (~7 s). tests/test_webapp_api.py 5/5 (số câu 1, quy tắc type lỗ, khoảng dự báo, cache đổi theo phiên bản). 16 bộ test PASS.
  - W3–W4: React 5 trang, menu trái, khoảng ngày trên URL (#ads?preset=28), điện thoại có nút Menu. Số khớp MCP tuần 8–14/11: 874 đơn, rev 48.380, MER 1,98, CPO 27,97; type lỗ Phone Case + AirPods Case, spend chưa gán type 29,63; dự báo 1.817 (1.246–2.388); báo động 13/11 mer + refunds, 11/11 Veterans Day.
  - Lỗi gặp khi kiểm, đã sửa: chuyển trang thì trang mới nhận nhầm số trang cũ → vỡ, trắng cả app (gắn nhãn trang + preset cho gói số, thêm Boundary bắt lỗi từng trang); nhãn cuối cột xuống dòng (vẽ nhãn 1 dòng); ô ABC bị cắt số (thu cỡ chữ hàng 5–6 ô); chữ trắng trên ô cohort xanh đậm ~2,8:1 (chữ tối); stop.bat có dấu làm cmd đọc sai (viết không dấu, tắt bằng PowerShell).
  - W6: webapp/start.vbs (chạy ẩn, log logs/webapp.log), webapp/stop.bat; đã thử tắt/bật, trả 200. Huy Anh tự tạo lối tắt trong shell:startup.
  - [ ] W5: kiểm thật sau lần Huy Anh chạy pipelines.run sáng 17/11: trang tự đổi "Kho cập nhật" và ngày trọn cuối 15/11 trong ≤ 60 giây.
  - [x] Huy Anh duyệt xoá bản Streamlit (16/11, xem mục Dọn dự án).
  - [x] Huy Anh tạo lối tắt Startup và mở được http://127.0.0.1:8600 (16/11).

## Dọn dự án (16/11, Huy Anh duyệt từng nhóm)
- [x] Xoá rác tự sinh: __pycache__ (10), transform/logs (11 MB), logs/run_2026-11-16.txt.
- [x] Xoá checks/_archive (7 script dùng 1 lần tuần 1 + README).
- [x] Xoá cổng morning đã bỏ: checks/gate.py, checks/gate/morning.csv, tests/test_gate.py, checks/sql/check_gate_cach_tinh.sql.
- [x] Xoá trang demo tuần 1: checks/demo_page.py, docs/demo-tuan-1.html, checks/present_page.py, docs/reference/store-report-orders-by-month.csv.
- [x] Xoá bản Streamlit: dashboard/app.py, charts.py, data.py, views/, .streamlit/, 2 mục launch.json. Giữ dashboard/queries.py + kpi.py (backend React dùng) và tests/test_dashboard.py (test kpi).
- [x] Chuyển 23 câu SQL kiểm từng bước vào checks/sql/da-kiem/ (giữ để học); check_tuan4_dap_an.sql ở ngoài (demo dùng). Sửa đường dẫn ở dbt_project.yml, metrics.yml, mart_rfm.sql.
- [x] Sửa chỗ còn nhắc: README (dashboard, gate, bảng thư mục, 15 bộ test), raw_spec.py, queries.py, docs/kham-pha-nguon-moi.md; requirements.txt thêm fastapi, uvicorn.
- [x] Kiểm: 15 bộ test PASS, backend vẫn trả 200, dbt_project.yml vẫn ASCII. Giữ lại có chủ đích: checks/explore_*, profile_sample.py, api_menu.py (cách khám phá nguồn mới ở docs/kham-pha-nguon-moi.md); data/ (cache Meta, cần cho nạp), bin/toolbox.exe, node_modules, dist, transform/target (tự sinh, đã trong .gitignore).


### Nhãn tuần thành khoảng ngày (16/11)
- [x] format.js thêm weekRange: '2026-11-08' → '08–14/11', qua tháng '27/09–03/10'. 4 biểu đồ theo tuần (Customers ×3, Products ×1) dùng cho trục và ô rê chuột ("Tuần 08–14/11"); minTickGap 14 để nhãn không đè nhau.
- [x] Kiểm: build OK; trục ở 1400px hiện 10 nhãn, cột cuối "08–14/11"; ô rê chuột cột cuối 729 mới + 145 cũ = 874 đơn, khớp tuần 8–14/11.

### Thêm dashboard vào kịch bản demo (16/11)
- [x] docs/demo-ban-giao.md: bước chuẩn bị 6 (mở tab dashboard, xem "Số mới nhất đã trọn"), bước 7 giấu tab vì Tổng quan có đáp án câu 1. Phần mới 19–22 phút: Tổng quan khớp câu 1, Quảng cáo & type tô đỏ type lỗ (chỉ trùng câu 4 khi ngày trọn mới nhất là thứ Bảy), tự có số mới trong ~1 phút. 5 câu mẫu rút còn 7–19 phút. Chữ trên giao diện đã đối với App.jsx, Ads.jsx.

## Claude trên dashboard: A + B (kế hoạch 16/11, Huy Anh duyệt)

Mục tiêu: trên http://127.0.0.1:8600 có trang **Hỏi Claude** (A: hỏi số, chỉ đọc) và **Báo cáo của tôi** (B: Claude đề xuất biểu đồ, Huy Anh bấm Lưu thì thành báo cáo, tự vẽ lại khi có số mới). Sửa 5 trang chính vẫn làm trong Claude Code app, không làm từ web.

Chốt cách gọi: Claude Code CLI đã đăng nhập gói Max (`claude -p`), không Claude API, không tốn thêm. Chỉ máy Huy Anh, chỉ Huy Anh dùng.

Khoá an toàn (đều kiểm bằng test):
- `--tools ""`: tắt hết tool có sẵn (Bash, Read, Edit...), Claude không chạm được file, không đọc được `.env`.
- `--strict-mcp-config --mcp-config .mcp.json` + `--allowedTools mcp__datae__* mcp__datae-sql__*`: chỉ 2 server chỉ đọc, khoá `datae-mcp`.
- Claude KHÔNG tự lưu báo cáo: nó chỉ trả một khối JSON đề xuất (tiêu đề, câu SELECT, kiểu biểu đồ, cột x/y). Backend tự kiểm: dry run BigQuery phải là SELECT, chỉ đọc gold/silver, dưới giới hạn byte; chạy bằng khoá chỉ đọc; Huy Anh xem trước rồi mới bấm Lưu.
- Mỗi lần 1 câu hỏi (khoá), quá 3 phút thì dừng.

Các bước:
- [ ] C0. Huy Anh chạy tay `claude -p "trả lời đúng một chữ: ok"` để chắc chế độ không giao diện chạy (dùng đăng nhập Max).
- [x] C1. `webapp/api/claude_chat.py`: dựng lệnh `claude -p` (stream-json, `--resume` để hỏi nối tiếp), đọc từng dòng, đẩy ra trang dạng SSE (chữ trả lời + "đang gọi tool X"); lời dặn hệ thống: tiếng Việt, ngày Phoenix, muốn biểu đồ thì trả khối `report`.
- [x] C2. `webapp/api/reports.py`: kiểm và lưu báo cáo vào `webapp/reports.json` (không vào git); chạy SQL theo phiên bản dữ liệu (cache như các trang); xoá báo cáo.
- [x] C3. Route: `POST /api/chat`, `POST /api/reports/preview`, `GET/POST/DELETE /api/reports`.
- [x] C4. React: trang **Hỏi Claude** (khung chat, hiện tool đang gọi, xem trước biểu đồ + nút Lưu) và trang **Báo cáo của tôi** (vẽ từng báo cáo, nút xoá). 1 component vẽ chung: cột, đường, bảng.
- [x] C5. Test (không gọi Claude thật, không BigQuery): lệnh có `--tools ""` và strict MCP; đọc khối report; chặn SQL không phải SELECT, chặn raw/pii, chặn spec sai.
- [ ] C6. Thử thật: Huy Anh gõ trên trang 2 câu (1 câu hỏi số, 1 câu "vẽ doanh thu theo product type 8 tuần"), lưu báo cáo, tải lại trang vẫn còn. Thử "đọc file .env" và "xoá bảng" phải bị chặn.
- [x] C7. README mục dashboard + kịch bản demo (thêm 1 phút nếu kịp), lessons nếu bị sửa.

Review A + B (16/11):
- Làm xong C1–C5, C7. `--bare` không dùng được (bỏ đăng nhập OAuth/Max), nên tách thư mục làm việc ra %LOCALAPPDATA%\DataE\claude-chat (ngoài dự án) + `--setting-sources project` để không nạp CLAUDE.md/settings của DataE. Gọi thẳng claude.exe, câu hỏi qua stdin (cmd.exe làm hỏng dấu nháy).
- Kiểm: tests/test_claude_chat.py 6/6 (khoá lệnh, dừng khi có tool lạ, stdin, 1 câu một lúc, chặn SQL ghi/nhiều câu/bảng raw/pii/dự án khác/>50 MB, lưu-xoá, cache theo phiên bản); 16/16 bộ test PASS. Trên trình duyệt: xem trước báo cáo thật 8 tuần (24 cột), Lưu → trang Báo cáo của tôi vẽ lại, xoá; SQL đọc raw bị BigQuery chặn (403). Báo cáo thử đã xoá.
- CHƯA kiểm: gọi Claude thật (C0, C6) vì dùng tài khoản Claude của Huy Anh, chờ Huy Anh chạy tay.

### Lưu bài phân tích (16/11, Huy Anh chọn "có")
- [x] 1 câu trả lời có thể có tối đa 3 biểu đồ (nhiều khối ```report).
- [x] Backend: webapp/analyses.json (không vào git), POST chạy lại các biểu đồ ngay lúc lưu và lưu kèm số (bản chụp cố định), ghi ngày lưu + ngày trọn cuối của số; GET, DELETE.
- [x] Trang Hỏi Claude: nút "Lưu bài phân tích" dưới mỗi câu trả lời (đặt tên, mặc định = câu hỏi). Trang Báo cáo của tôi: 2 phần Bài phân tích (bản chụp) và Biểu đồ (tự cập nhật).
- [x] Test + kiểm trình duyệt; README.
- Review: kiểm bằng tests/test_claude_chat.py (7/7: nhiều khối report, tối đa 3; bài lưu giữ số lúc lưu dù kho đổi; ghi data_until = ngày trọn cuối; bài lỗi không lưu) và trình duyệt (bài kèm 2 biểu đồ lưu, mở lại thấy chữ + 2 biểu đồ, xoá). Dữ liệu thử đã xoá. Vẫn chờ Huy Anh đăng nhập `claude` để thử Claude thật.
- 16/11 Huy Anh chốt: trước mắt hỏi số bằng Claude Code app trên máy. Trang Hỏi Claude giữ nguyên (code + test xong), C0/C6 hoãn tới khi Huy Anh đăng nhập `claude` bằng gói Max trong terminal; chưa đăng nhập thì trang chỉ báo lỗi trong khung chat.

## Chọn ngày trong trang + hiện hoàn đơn (kế hoạch 16/11, Huy Anh duyệt)
Số thật 28 ngày 18/10–14/11 (MCP chỉ đọc): 34 đơn có hoàn, 1.111,74 $ (theo ngày hoàn, fct_orders); theo dòng sản phẩm hoàn 29 cái, ~892 $ (Long Sleeve 10 cái 329 $, Phone Case 10 cái 323 $, Ornament 6, AirPods Case 1/52 = 1,9%).
- [x] H1. Bỏ khối "Khoảng ngày" khỏi menu trái; đặt nút 7/14/28 ngày/Tháng này ngay dưới tiêu đề của 5 trang số (trang Claude không có). URL #trang?preset= giữ nguyên.
- [x] H2. Tổng quan: thêm ô "Hoàn tiền": số đơn có hoàn + tiền hoàn trong kỳ (theo NGÀY HOÀN, fct_orders.first_refund_date / total_refunded), so kỳ trước.
- [x] H3. Sản phẩm: mục "Hoàn trả theo dòng sản phẩm" (bảng: bán, cái hoàn, % hoàn, tiền hoàn; theo NGÀY ĐẶT của đơn, fct_lines quantity − current_quantity, line_gross_after_discounts − line_revenue) + 5 mẫu hoàn nhiều nhất. Ghi chú: khác số ở Tổng quan vì hoàn tiền ship/hoàn một phần không gắn dòng sản phẩm, và tính theo ngày đặt.
- [x] H4. Test (test_webapp_api) + build + kiểm trình duyệt so với số MCP ở trên.
- Review: API 28 ngày khớp số MCP tra trước: Tổng quan 1.111,74 $ / 34 đơn (kỳ trước 505,20 $ / 22, ▲120%); Sản phẩm 29/5.260 cái (0,55%), 892,80 $, Long Sleeve 10 cái 329,42 $. Nút ngày dưới tiêu đề, menu trái hết khối Khoảng ngày, điện thoại 375px xuống 2 hàng không cuộn ngang. test_webapp_api thêm 1 test (NaN kỳ trước, số kỳ, % hoàn); 16/16 bộ PASS.

### Nền sáng/tối + bỏ biểu đồ 12 tuần ở Sản phẩm (16/11, Huy Anh chọn "có nút đổi")
- [x] Nền sáng mặc định, nút "☾ Nền tối / ☀ Nền sáng" ở menu trái, nhớ lựa chọn (localStorage, hỏng thì về sáng). CSS token :root + [data-theme]; màu biểu đồ format.js THEMES, C đổi tại chỗ, trang vẽ lại (key theo nền); trục/lưới đọc màu lúc vẽ (getter).
- [x] Bảng màu nền sáng chạy validate_palette.js trên #FFFFFF: đủ 5 PASS (teal #15936F, vàng #B07600 đậm hơn 1 bậc để ≥ 3:1). Chữ: teal #0B7A5C 5:1 trên trắng, muted 6,2:1, đỏ lỗ #C42B2B 5,6:1.
- [x] Bỏ "Doanh thu theo dòng sản phẩm, 12 tuần" ở Sản phẩm (không theo bộ lọc ngày; Huy Anh: không cần thì bỏ) + câu SQL LINE_WEEKLY.
- [x] Kiểm: build OK, 16/16 test PASS; trình duyệt: mặc định sáng, trục #556179, lưới #E1E6EF, ô cohort đúng thang sáng; bấm nút thành tối (màu tối gốc), lưu "dark"; bấm lại về sáng.
- [x] 16/11: cột "Tiền hoàn" đổi thành "Tổng tiền hoàn" + thêm "TB mỗi cái" (2 bảng hoàn trả ở Sản phẩm); dòng giải thích tô đỏ (≥ 1%, ngưỡng tạm) chuyển lên chú thích ngay trên bảng dòng sản phẩm. Kiểm trình duyệt 14 ngày: Phone Case 5 cái 168,98 $ → 33,80 $/cái.
- [x] 16/11: Khách & email không còn bộ lọc ngày (mọi mục cố định: 12 tuần, mua lần 2 60 ngày, RFM, cohort); đầu trang ghi "số tới <ngày trọn cuối>"; luôn đọc 1 bản cache. Kiểm trình duyệt: trang không có nút ngày, 5 mục vẫn hiện, Tổng quan vẫn có nút.
- [x] 16/11 sửa lỗi: mart_product_abc lấy max(order_date) làm cuối cửa sổ nên tính lẫn ngày đang dở (trang ghi 18/08 → 15/11 khi ngày trọn cuối là 14/11). Đổi thành max − 1 như mart_repeat_60d, sửa mô tả cột. CHƯA build: chờ lần pipelines.run tay tới (có dbt build).
- [x] Sản phẩm: Top species + Hoàn trả (theo bộ lọc) lên đầu, ABC xuống cuối, tiêu đề "cố định 90 ngày" + chú thích "Không theo bộ lọc ngày" (Huy Anh duyệt 16/11). Kiểm trình duyệt: thứ tự đúng, không lỗi.
- [x] 16/11: Cảnh báo & dự báo không còn bộ lọc ngày (luôn 14 ngày gần nhất + dự báo 14 ngày tới, backend chỉ dùng end_max). Kiểm trình duyệt: không có nút ngày, 2 mục hiện, đầu trang "số tới 14/11/2026". Còn bộ lọc: Tổng quan, Quảng cáo & type, Sản phẩm.
- [x] 16/11 sửa: shortcut Startup DataLake.lnk trỏ "D:\Th?c t?p\..." nên không chạy. Ghi lại bằng Shell.Application: wscript.exe "…\webapp\start.vbs", thư mục làm việc webapp. Kiểm: đọc lại 3 trường đều tồn tại; tắt backend, chạy đúng shortcut đó → cổng 8600 lên, /api/meta 200. Máy chưa khởi động lại từ 15/11 20:56 (chỉ ngủ), nên lần thử thật là lần khởi động tới.

### Đưa lên GitHub (16/11, Huy Anh: repo của mình trước, chưa cần repo công ty)
- [x] git init (main, core.autocrlf false), .gitignore có sẵn chặn .env, secrets/, data/, logs/, bin/, node_modules, dist, reports.json, analyses.json. Quét nội dung: không token Shopify/Meta/Klaviyo/Google/GitHub, không private key; email trong test là example.com. Có mã tài khoản Meta act_… trong tasks/todo.md (định danh, không phải bí mật; repo private).
- [x] Repo PRIVATE https://github.com/HapCT/DataE, commit d04a8ba. Kiểm trên GitHub: 173 file, 0 file khoá/.env/data/logs/bin.
- [ ] Khi anh Quang chốt repo công ty: chuyển (transfer) hoặc thêm remote mới.
- [x] 16/11 kiểm guardrail brief cho bản đã đẩy: không token/khoá; PII (email thật, SĐT, địa chỉ, mã bang+zip, mã khách băm 64 hex) không có trong 173 file; không có lịch chạy tự động (cron/schtasks); nguồn chỉ đọc (Shopify POST chỉ là GraphQL + bulkOperationRunQuery tạo job đọc). Chặn Meta theo giờ Phoenix có test (test_limits, test_run).

## Sửa "ngày đã trọn" theo thời điểm nạp (kế hoạch 16/11, Huy Anh duyệt)
Lỗi: nạp 14:07 VN = 00:07 Phoenix 16/11, ngày 16/11 chưa có đơn nên max(order_date) = 15/11 bị coi là ngày dở; dashboard dừng 14/11 dù 15/11 đủ 169 đơn. MCP today_phoenix (theo đồng hồ) nói 15/11 → 2 nơi lệch nhau.
- [x] N1. pipelines.run: ghi complete_through = (ngày Phoenix lúc BẮT ĐẦU kéo Shopify) − 1, truyền cho dbt build dạng var.
- [x] N2. dbt: macro complete_through() = var đó, thiếu var (dbt chạy tay) thì lùi về max(order_date) − 1 như cũ; bảng gold.load_status 1 dòng (complete_through, loaded_at).
- [x] N3. Thay "max(order_date) − 1" bằng macro ở các mart (repeat_60d, product_abc, anomaly_daily, rfm, cohort_retention, cohort_clv, dim_customer: xem từng chỗ, chỉ đổi chỗ nghĩa là "ngày trọn").
- [x] N4. Dashboard: end_max = min(ngày trọn theo đồng hồ, load_status.complete_through). MCP today_phoenix trả thêm "kho có số trọn tới".
- [x] N5. Test + Huy Anh chạy tay dbt build + forecast.publish (16/11). Kiểm (khoá chỉ đọc): load_status 15/11 'lúc nạp'; ABC, anomaly, repeat_60d tới 15/11; forecast mốc 15/11 (dự báo từ 16/11); dashboard end_max 15/11, 7 ngày 9–15/11 = 931 đơn (khớp reconcile Shopify 931), Rev 51.281,58, MER 2,00.
- [x] 16/11 reconcile sau lần nạp 14:07: Shopify 931/931 ✓, Klaviyo Placed Order 931/931 ✓, Meta lệch 1/7 ngày: 15/11 nguồn 4.650,52 kho 4.645,68 (−4,84 USD). Lý do: nạp lúc 00:12 Phoenix, Meta còn cập nhật spend của ngày vừa hết; lần nạp sau lấy lại 7 ngày sẽ tự khớp (kiểm lại).
- [x] 14/11 email_orders = 0 KHÔNG phải thiếu dữ liệu: Klaviyo có đủ 130 Placed Order ngày 14/11 (= 130 đơn Shopify) nhưng gán 0 cho campaign và 0 cho flow (13/11: 2 + 5, 15/11: 1 + 8). Là tín hiệu nghiệp vụ: báo anh Quang xem flow/gửi email ngày 14/11 có bị dừng không.
- Review N1–N4 (16/11): load_shopify ghi data/last_load.json lúc BẮT ĐẦU kéo; pipelines.dbt tự thêm --vars complete_through cho build/run/test/compile; macro complete_through() = least(var, max(order_date)), thiếu var thì max − 1 như cũ; gold.load_status. Đổi: mart_repeat_60d, mart_product_abc, mart_anomaly_daily (+ test anomaly_hop_ly), forecast/backtest. GIỮ NGUYÊN: mart_rfm (ảnh chụp tới đơn mới nhất), cohort/clv (tháng cuối có dữ liệu), dim_customer (đơn cuối của khách). Dashboard: min(đồng hồ, load_status), chưa có bảng thì lùi về cách cũ; data_version bỏ qua bảng chưa dựng. MCP today_phoenix trả thêm data_complete_through, use_until. Bỏ kpi.end_day (quy tắc cũ). Sửa chữ: tools.yaml, claude_chat, Overview, kpi, demo, đáp án tuần 4 (đọc load_status).
- Kiểm: 16/16 bộ test PASS (thêm test ghi mốc nạp, --vars, dashboard 15/11 khi nạp 00:07 Phoenix, lùi về cách cũ khi thiếu bảng, MCP use_until). Đã ghi data/last_load.json từ log lần nạp 07:07:36 UTC (→ 15/11). CHƯA: dbt build thật (Huy Anh chạy tay) rồi kiểm dashboard 15/11, ABC/anomaly/repeat tới 15/11, forecast mốc 15/11.
