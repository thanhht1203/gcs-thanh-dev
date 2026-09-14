# GCS Windows

Phần mềm giao diện điều khiển (Electron + React).

```bash
npm install
npm run electron:dev
```

Chỉ trình duyệt: `npm run dev` rồi mở http://127.0.0.1:5173

Đóng gói installer:

```bash
npm run electron:build
```

File ra `gcs/release/`.

Ô kết nối trên thanh trên: `ws://<IP-Jetson>:8765/ws`

Nút **Cấu hình** mở panel:
- **GCS**: URL WebSocket, độ rộng sidebar, chiều cao hàng dưới, hiện/ẩn PiP & bản đồ (lưu localStorage)
- **Jetson**: chỉnh toàn bộ `config.yaml` rồi **Lưu & hot-apply** (mở lại thiết bị không restart service)

