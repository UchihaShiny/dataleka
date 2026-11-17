# GitHub và Cloudflare — bàn giao triển khai

Repo đề xuất: **dataleka**, PRIVATE, trên tài khoản GitHub cá nhân đã được bạn xác minh. Không đẩy .env, secrets, data, logs, kho lưu reports/analyses, .venv, node_modules hoặc cấu hình IDE. Không đổi remote origin hiện tại.

## Toàn bộ app khác với frontend

Ứng dụng này có FastAPI/Pandas/BigQuery, CLI Claude chạy subprocess và JSON storage trên ổ đĩa. Không thể coi upload thư mục dist vào Pages là triển khai đủ ứng dụng. Python Workers hỗ trợ FastAPI/ASGI, nhưng điều đó không chứng minh subprocess, thread và storage của app này tương thích. Chưa port hoặc kiểm thử Worker runtime.

Nguồn chính thức:
- https://developers.cloudflare.com/workers/languages/python/packages/fastapi/
- https://developers.cloudflare.com/pages/get-started/git-integration/
- https://developers.cloudflare.com/pages/get-started/direct-upload/

## Mở workspace Cloudflare

Vào https://dash.cloudflare.com/ → chọn account → Workers & Pages.

Để đưa frontend vào Pages bằng GitHub: Create application → Pages → Connect to Git, chọn repo mới. Root directory `webapp/web`, build command `npm run build`, output `dist`, Node 22. Kết nối Git có thể bật tự động deploy khi push; chưa thực hiện thao tác này trong phiên.

**Frontend riêng chưa có API**: các route /api cần backend được triển khai và bảo vệ riêng, cùng một origin hoặc proxy được xác minh. Không bật bản public rồi nhập credential chỉ để làm màn hình hết lỗi. Không có fallback demo sau lỗi live.

## Hướng toàn bộ ứng dụng

`deployment/Dockerfile` đóng gói React build + FastAPI cho môi trường container phù hợp. Cloudflare Containers/Worker routing hoặc một Python host phía sau Cloudflare là hướng cần xác minh với workspace/account của bạn; Dockerfile này chưa được build/chạy và chưa phải cấu hình Cloudflare Containers hoàn chỉnh. Không có wrangler deploy hay schedule nào được kích hoạt.

Trước live cần xác thực người dùng, persistence bền vững và khóa BigQuery chỉ đọc. CLI Claude cần môi trường đã đăng nhập; không chuyển khóa pipeline lên cloud. File JSON lưu hiện tại phù hợp localhost một người dùng. Mặc định container là demo tường minh, không credential.

## GitHub dataleka

GitHub CLI chính thức đã được xác thực cho tài khoản cá nhân **UchihaShiny**. Đích là `UchihaShiny/dataleka` PRIVATE. Chạy `bash scripts/publish_github.sh` để đóng gói và quét nguồn, tạo repo, push main và so SHA remote với local. Script từ chối ghi đè repo đã tồn tại; workspace/index/origin ban đầu được giữ nguyên.

`data/release/dataleka-source.zip` là snapshot nguồn cùng manifest SHA256; không chứa credential, dữ liệu runtime hay saved content. Quy trình ZIP và publish đã có 4 regression offline. Kết quả thật của lần push được CLI in và chỉ coi là thành công khi private visibility và SHA đã được xác minh.

Cloudflare chưa deploy; Dockerfile chưa build do không có Docker, Python Worker chưa port. GitHub Actions chỉ có workflow_dispatch để chạy kiểm tra thủ công, không cron, ingestion hay deploy.
