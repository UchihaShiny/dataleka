# Checklist khám phá một nguồn dữ liệu mới

Dùng khi gặp một vùng dữ liệu chưa ai biết đọc thế nào. Mục tiêu: sau **1 buổi** trả lời được 4 câu: **có gì**, **thật sự trông thế nào**, **trường nào dùng được**, **nối ra sao và số nghĩa là gì**. Chưa xong checklist thì chưa pull lịch sử, chưa vào BigQuery.

Đã thử trên Shopify, Meta, Klaviyo (ngày mẫu 7/11/2026). Kết quả mẫu: `docs/present-3-nguon.html`, `docs/meta-schema.md`.

---

## 0. Trước khi bắt đầu

- [ ] **Nguồn này trả lời câu hỏi kinh doanh nào?** Viết 1 câu. Ví dụ: Shopify là "bán được gì", Meta là "tiêu tiền quảng cáo vào đâu", Klaviyo là "email làm gì".
- [ ] **Quyền truy cập:** token hoặc key **chỉ đọc**, cấp riêng cho mình, không dùng chung `.env` của người khác. Ghi lại các quyền đang có.
- [ ] **Giới hạn gọi API:** bao nhiêu lần mỗi phút hoặc mỗi giờ? Có dùng chung với đội khác không (Meta dùng chung app với đội ads)? Có giờ nào không được chạy?
- [ ] **PII:** nguồn có email, tên, số điện thoại, địa chỉ, IP không? Liệt kê để bỏ ngay từ câu truy vấn.
- [ ] **Múi giờ và tiền tệ** của nguồn (DEERLY dùng America/Phoenix, USD).
- [ ] **Chọn 1 ngày mẫu:** ngày đã kết thúc và đã có số để đối chiếu (ví dụ số đơn của ngày đó trên Shopify).

## 1. Hỏi nguồn tự mô tả: có những gì?

Làm:
- [ ] Hỏi API danh sách trường nếu có (GraphQL introspection, `?metadata=1`, OpenAPI spec). Nếu không có thì dùng trang reference của tài liệu.
- [ ] Liệt kê các **đối tượng** (bảng) và các **connection** giữa chúng.
- [ ] Lưu danh sách trường ra `data/explore/<nguồn>/_schema_<đối tượng>.json`.

Đầu ra:
- [ ] Danh sách đối tượng, và số trường của mỗi đối tượng.

Lỗi hay gặp:
- API tự mô tả có thể đã bị bỏ: Meta v27 trả `metadata` rỗng. **Kiểm kết quả có rỗng không**, đừng tin là đã chạy.
- Tài liệu có thể lệch với phiên bản đang dùng. Ghi rõ phiên bản API.

## 2. Lấy mẫu 1 ngày: dữ liệu thật trông thế nào?

Làm:
- [ ] Lấy **đúng dữ liệu của ngày mẫu**, xin **đủ mọi trường** từ bước 1 (trừ PII).
- [ ] Bộ lọc ngày ghi **mốc giờ đầy đủ có múi giờ** (`2026-11-07T00:00:00-07:00`). Không ghi chỉ ngày.
- [ ] Trường nào bị nguồn từ chối (không tồn tại, thiếu quyền) thì **tự bỏ, ghi lý do** vào `_dropped.json`, rồi gọi lại. Đặt giới hạn số lần thử để giữ quota.
- [ ] Lưu nguyên JSON ở `data/explore/<nguồn>/<bảng>.json` (trên máy, gitignore). **Không ghi BigQuery.**
- [ ] Ghi số lần gọi và mức dùng quota của lượt chạy.

Đầu ra:
- [ ] Mỗi bảng một file mẫu, kèm số bản ghi.

Lỗi hay gặp:
- Shopify `created_at:<2026-11-01` tính luôn cả ngày 1/11. Klaviyo hiểu mốc giờ không ghi offset là UTC.
- Bộ lọc theo danh sách id không phải đối tượng nào cũng nhận (Meta `adcreatives`). Tìm đường khác, ví dụ lấy lồng trong đối tượng cha.
- Xin nhiều dữ liệu một lần có thể làm nguồn quá tải (Meta trả mã 1, mã 2). Chia nhỏ khoảng ngày.

## 3. Profile: trường nào dùng được?

Làm:
- [ ] Chạy `python checks/profile_sample.py <nguồn>`. Script duỗi JSON lồng nhau thành đường dẫn trường; mỗi trường có tỉ lệ có giá trị, kiểu, số giá trị khác nhau và một ví dụ.
- [ ] Đọc `data/explore/<nguồn>/profile.md`, đánh dấu:
  - [ ] Trường **luôn trống**: bỏ.
  - [ ] Trường **khoá** (id, số giá trị khác = số bản ghi).
  - [ ] Trường **khoá nối** sang bảng khác (`*_id`).
  - [ ] Trường **tiền, số, ngày giờ**: kiểu gì, đơn vị gì (xu hay đồng, UTC hay giờ địa phương).
  - [ ] Trường **mảng hoặc JSON lồng nhau**: bên trong có gì.

Đầu ra:
- [ ] Mỗi bảng có: **grain** (mỗi dòng là gì), **khoá**, các trường đáng lấy, các trường bỏ.

Lỗi hay gặp:
- Số lưu dạng chuỗi (`"10.50"`), tiền lưu bằng xu (`daily_budget` của Meta).
- Một bảng có thể là số cộng dồn không cộng được (`reach`, `frequency`).

## 4. Kiểm quan hệ và ý nghĩa: nối thế nào, số nghĩa là gì?

Làm:
- [ ] **Vẽ sơ đồ** các bảng: cha → con, ghi `1 : n` hoặc `1 : 1`, kèm số dòng mẫu.
- [ ] **Kiểm khoá nối:** mỗi khoá con có tìm thấy cha không? Đếm số mồ côi.
- [ ] **Kiểm grain:** một khoá có lặp lại không? Một con có đổi cha theo thời gian không?
- [ ] **Kiểm tổng qua nhiều cấp:** cộng số ở các cấp phải bằng nhau. **Phải dùng các lần gọi độc lập**; cộng cùng một bảng theo nhiều cấp thì luôn bằng nhau, không chứng minh gì.
- [ ] **So với nguồn sự thật:** cùng ngày đó, nguồn này nói bao nhiêu đơn, bao nhiêu tiền, so với Shopify thì sao?
- [ ] **Tìm tên trùng nghĩa:** một sự kiện có nằm dưới nhiều tên không (Meta: 1 lượt mua mang 8 tên `action_type`)?
- [ ] **Tìm trạng thái "của hôm nay":** trường nào là ảnh chụp hiện tại chứ không phải của ngày mẫu (Meta `effective_status`)?
- [ ] **Tìm đường nối sang nguồn khác:** id chung, SKU, UTM, email đã hash.

Đầu ra:
- [ ] Sơ đồ quan hệ.
- [ ] Danh sách bẫy, mỗi bẫy có ví dụ số thật.
- [ ] Ý nghĩa kinh doanh của các số chính, và **nên tin số nào, không nên tin số nào**.

## 5. Chốt và ghi lại

- [ ] Viết `docs/<nguồn>-schema.md`: sơ đồ, bảng (grain, khoá, khoá nối, trường lấy, trường bỏ), bẫy, cơ hội nối, đề xuất bảng raw.
- [ ] Liệt kê **câu hỏi cần người duyệt chốt**: trường nào lấy, mốc lịch sử, nhịp nạp.
- [ ] **Duyệt xong mới** viết pipeline, nạp `raw`, rồi pull lịch sử.

---

## Code dùng lại

| Việc | File | Ghi chú |
|---|---|---|
| Lưu mẫu, profile | `checks/profile_sample.py` | Dùng chung mọi nguồn. Tự ẩn ví dụ của trường giống PII |
| Lấy mẫu từng nguồn | `checks/explore_<nguồn>.py` | Mỗi nguồn một file nhỏ; gọi API qua client của pipeline để giữ quota |
| Test | `tests/test_explore.py` | Thêm case phản hồi giả cho nguồn mới trước khi chạy token thật |

## Nguyên tắc

- Chỉ đọc. Không ghi gì vào nguồn.
- Script dùng token thật thì người có token chạy; viết và test bằng phản hồi giả trước.
- Mẫu chỉ nằm trên máy, không PII, không commit.
- Một nguồn, một ngày, một buổi. Chưa hiểu thì chưa pull.
