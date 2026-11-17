# Cài đặt BigQuery cho DataE

Làm một lần, khoảng 15 phút, trên trình duyệt. Sau khi làm xong:
- Có một project Google Cloud chạy BigQuery Sandbox (không cần thẻ) để demo.
- Có một service account chỉ có 2 quyền: ghi dữ liệu BigQuery và chạy truy vấn.
- Có một file khoá JSON nằm ở `D:\Thực tập\DataE\secrets\`.



> Không dán nội dung file khoá JSON vào chat, Lark hay Git. Ai có file này cũng ghi được vào BigQuery của bạn.

## 1. Tạo project

1. Mở https://console.cloud.google.com và đăng nhập bằng tài khoản Google bạn định dùng.
2. Bấm ô chọn project ở thanh trên cùng, rồi chọn **New Project**.
3. **Project name**: `datae`. Google sẽ tự tạo **Project ID** (của bạn là `datae-514203`). Hãy ghi lại ID này, sau dùng cho `GCP_PROJECT_ID`.
4. Bấm **Create**, chờ vài giây, rồi chọn đúng project vừa tạo ở ô chọn project.

## 2. Không gắn thẻ (BigQuery Sandbox)

DataE là demo nên chạy trên Sandbox: không cần thẻ, vẫn có 1 TB truy vấn và 10 GB lưu trữ miễn phí mỗi tháng. Dùng quá giới hạn thì Google chỉ chặn truy vấn, không tính tiền.

Nếu Google mở trang **Try Google Cloud for free** hay **Payment Information Verification**, cứ đóng trang đó lại, không cần nhập thẻ.

Giới hạn cần biết: bảng tự xoá sau 60 ngày, và không chạy được `INSERT`, `MERGE`, `DELETE`. Code của DataE đã được viết để tránh các lệnh này.

## 3. Bật BigQuery API

1. Mở https://console.cloud.google.com/apis/library/bigquery.googleapis.com?project=datae-514203
2. Kiểm tra ô project đang là `datae`, rồi bấm **Enable**. Nếu thấy chữ **API Enabled** thì nghĩa là đã bật sẵn.

## 4. Tạo service account

1. Mở menu ☰, chọn **IAM & Admin**, rồi **Service Accounts**, rồi **Create service account**.
2. **Service account name**: `datae-pipeline`, rồi bấm **Create and continue**.
3. Ở phần **Grant this service account access to project**, thêm đúng 2 role:
   - `BigQuery Data Editor`: để tạo dataset, tạo bảng và ghi dữ liệu
   - `BigQuery Job User`: để chạy truy vấn và job nạp dữ liệu
4. Bấm **Continue**, rồi **Done**. Không chọn role `Owner` hay `Editor`, vì 2 role đó có quyền với toàn bộ project.

## 5. Tải khoá JSON

1. Trong danh sách Service Accounts, bấm vào `datae-pipeline@...`.
2. Chọn tab **Keys**, rồi **Add key**, rồi **Create new key**, chọn **JSON**, rồi **Create**. Một file `.json` sẽ tự tải về.
3. Tạo thư mục `D:\Thực tập\DataE\secrets\` rồi chuyển file vào đó, đổi tên thành `datae-pipeline.json`.

Nếu Google báo *Service account key creation is disabled*, tức là tài khoản của bạn thuộc một tổ chức đang chặn tạo khoá. Khi đó báo mình, mình sẽ chuyển sang đăng nhập bằng `gcloud` thay cho file khoá.

## 6. Điền `.env`

Mở `D:\Thực tập\DataE\.env` và thêm 3 dòng sau, thay ID bằng Project ID của bạn:

```text
GCP_PROJECT_ID=datae-514203
GOOGLE_APPLICATION_CREDENTIALS=secrets/datae-pipeline.json
BQ_LOCATION=US
```

`BQ_LOCATION=US` là nơi đặt dữ liệu. Shop dùng giờ Mỹ, và các khu vực đều có cùng free tier. Đã tạo dataset rồi thì không đổi được location, nên hãy giữ `US`.

## 7. Kiểm kết nối

Từ thư mục `D:\Thực tập\DataE`, chạy:

```bash
python checks/check_bigquery.py
```

Kết quả đúng sẽ in ra project, service account, location, kết quả `select 1` và số dataset hiện có (lần đầu là 0). Script này chỉ đọc. Nó không tạo bảng, và không đụng tới Shopify hay Meta.

## 8. Khoá chỉ đọc cho MCP

Brief yêu cầu MCP (Claude đọc số) dùng khoá riêng **chỉ đọc**, không dùng khoá `datae-pipeline` có quyền ghi. Lỡ Claude bị dụ chạy câu lệnh lạ thì khoá này cũng không xoá hay sửa được gì, và không đọc được dữ liệu cá nhân (`pii`) hay `raw`.

**a. Tạo service account** (như mục 4, nhưng khác role):
1. **IAM & Admin** → **Service Accounts** → **Create service account**.
2. **Service account name**: `datae-mcp` → **Create and continue**.
3. Thêm đúng **1 role** ở cấp project: `BigQuery Job User` (chỉ để chạy truy vấn). **Không** thêm `BigQuery Data Editor`, `Data Viewer` hay role nào khác ở cấp project, vì role cấp project có hiệu lực với mọi dataset, kể cả `pii`.
4. **Continue** → **Done**.

**b. Cho đọc riêng dataset `gold`:**
1. Mở BigQuery Studio, ở khung Explorer bấm vào dataset `gold` → **Share** (hoặc dấu ⋮ → **Share**) → **Manage permissions** → **Add principal**.
2. **New principals**: `datae-mcp@datae-514203.iam.gserviceaccount.com`. **Role**: `BigQuery Data Viewer` → **Save**.
3. Không làm bước này với `raw`, `pii`. Silver làm riêng ở mục 9 (cần thêm 1 bước vì silver là view đọc từ raw).

**c. Tải khoá và điền `.env`:**
1. Vào **IAM & Admin** → **Service Accounts**. Trong danh sách, bấm vào dòng email `datae-mcp@datae-514203.iam.gserviceaccount.com` (bấm vào chữ email, không phải ô chọn).
2. Ở trang mới, chọn tab **Keys** ở hàng tab phía trên (cạnh Details, Permissions).
3. Bấm **Add key** → **Create new key** → chọn **JSON** → **Create**. Trình duyệt tự tải 1 file về thư mục `Downloads`, tên dạng `datae-514203-1a2b3c4d5e6f.json`. Bấm **Close**. Google chỉ cho tải file này 1 lần; mất thì phải tạo khoá mới.
4. Chuyển file vào `secrets` và đổi tên thành `datae-mcp.json`. Bằng File Explorer: cắt file trong `Downloads`, dán vào `D:\Thực tập\DataE\secrets\` (cạnh `datae-pipeline.json`), rồi đổi tên. Hoặc chạy trong PowerShell (thay đúng tên file vừa tải):

```powershell
Move-Item "$HOME\Downloads\datae-514203-1a2b3c4d5e6f.json" "D:\Thực tập\DataE\secrets\datae-mcp.json"
```

5. Mở file `D:\Thực tập\DataE\.env` trong Antigravity. Bên trong đã có dòng `GOOGLE_APPLICATION_CREDENTIALS=secrets/datae-pipeline.json`. Xuống cuối file, thêm **1 dòng mới**, viết y hệt (không dấu cách quanh dấu `=`, không dấu nháy):

```text
MCP_CREDENTIALS=secrets/datae-mcp.json
```

6. Bấm **Ctrl+S** để lưu (Antigravity hay để file chưa lưu, tab có chấm tròn là chưa lưu). Không sửa dòng `GOOGLE_APPLICATION_CREDENTIALS`: pipeline vẫn dùng khoá cũ.

**d. Kiểm:**

```bash
python checks/check_mcp_key.py
```

Đúng thì in 7 dấu ✓ (sau khi làm cả mục 9): đọc được 2 bảng gold, 2 bảng silver; KHÔNG đọc được `raw.shopify_orders`, `pii.shopify_customers`; KHÔNG tạo được bảng trong `gold`. Sau đó chạy `python checks/check_mcp_sql.py` (dry run bằng chính khoá MCP), rồi mở phiên Claude mới để MCP nạp khoá mới.

Pipeline, dbt và `forecast.publish` vẫn dùng khoá `datae-pipeline` như cũ. Chưa có dòng `MCP_CREDENTIALS` thì MCP tạm dùng khoá pipeline và in cảnh báo.

## 9. Cho khoá MCP đọc silver (tuần 4)

Brief tuần 4: khoá MCP đọc `silver` + `gold`. Khó ở chỗ: phần lớn bảng silver là **view** đọc từ `raw`. BigQuery bình thường bắt người đọc view phải có quyền đọc cả bảng gốc, mà khoá MCP cố ý không có quyền `raw`. Cách chuẩn là **authorized dataset**: cho cả dataset `silver` được đọc `raw` thay người dùng. Khoá MCP đọc view silver được, còn mở thẳng `raw` vẫn bị chặn. Silver không có dữ liệu cá nhân (khách chỉ là `customer_key` mã hoá từ email; Klaviyo chỉ là số đếm).

Làm bằng tài khoản Google của bạn (chủ project), trên BigQuery Studio:

**a. Cho `silver` được đọc `raw`:**
1. Khung **Explorer** bên trái → mở project `datae-514203` → bấm vào dataset **`raw`** (bấm chữ, không phải mũi tên).
2. Thanh phía trên bảng thông tin dataset → **Share** (hoặc dấu ⋮ cạnh `raw` → **Share**) → chọn **Authorize Datasets** (có bản giao diện để trong mục **Sharing** → **Authorize Datasets**).
3. Ô **Dataset ID**: chọn hoặc gõ `datae-514203.silver` → **Add authorization** → đóng khung.
4. Không cấp gì cho `datae-mcp` ở dataset `raw`.

**b. Cho khoá MCP đọc `silver`:** như mục 8b, nhưng bấm vào dataset **`silver`** → **Share** → **Manage permissions** → **Add principal** → `datae-mcp@datae-514203.iam.gserviceaccount.com`, role **BigQuery Data Viewer** → **Save**.

**c. Kiểm:**

```bash
python checks/check_mcp_key.py
```

Đúng thì in 7 dấu ✓, có thêm `đọc được silver.stg_orders` và `đọc được silver.product_lines`, và vẫn `KHÔNG đọc được raw.shopify_orders`. Nếu `silver.stg_orders` báo 403 mà `silver.product_lines` đọc được thì bước a chưa lưu (hoặc chọn nhầm dataset).

dbt build tạo lại view bằng `CREATE OR REPLACE VIEW` không làm mất quyền ở bước a, vì quyền gắn với cả dataset `silver`, không gắn với từng view.

## 10. MCP Toolbox: Claude tự viết SQL trên silver + gold (tuần 4)

Server `datae` có 15 tool viết sẵn SQL. Câu hỏi nằm ngoài các tool đó thì Claude dùng server thứ hai `datae-sql` (MCP Toolbox for Databases của Google) để tự viết câu SELECT. Cấu hình ở `mcp_toolbox/tools.yaml`: chỉ SELECT (`readOnly`, `writeMode: blocked`), chỉ dataset `silver`, `gold` (`allowedDatasets`), tối đa 200 MB mỗi câu. Khoá là `datae-mcp` lấy từ `.env` (`MCP_CREDENTIALS`), qua `mcp_toolbox/run.py`.

**a. Tải toolbox.exe** (295 MB, đã kiểm 13/11), đặt ở `bin\` (đã nằm trong `.gitignore`):

```powershell
curl.exe -L -o "D:\Thực tập\DataE\bin\toolbox.exe" https://storage.googleapis.com/mcp-toolbox-for-databases/v1.16.0/windows/amd64/toolbox.exe
```

```powershell
(Get-FileHash "D:\Thực tập\DataE\bin\toolbox.exe").Hash
```

Phải ra `326C9783187F7A3D639BAA0A2A78EF3F452EA945AA31B6D5FF82F75D505B7E7F`. Khác thì xoá file, không chạy.

**b. Kiểm:**

```bash
python checks/check_toolbox.py
```

Đúng thì 6 dấu ✓: đọc được gold, silver; `get_table_info` có mô tả cột; từ chối `raw`, `pii` và câu `create table`.

**c. Nối vào Claude Code:** `.mcp.json` đã có server `datae-sql`. Mở phiên Claude mới (MCP chỉ nạp lúc khởi động phiên), duyệt server khi được hỏi.
