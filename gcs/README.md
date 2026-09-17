# GCS Windows

Phần mềm giao diện điều khiển EO (Electron + React + Zustand).

## Chạy

```bash
cd gcs
npm install
npm run electron:dev
```

Chỉ trình duyệt: `npm run dev` → http://127.0.0.1:5174 (port theo `vite.config.ts`).

## Đóng gói

```bash
npm run electron:build
```

Installer ra `gcs/release/`.

## Kết nối Jetson

Ô URL trên thanh trên, ví dụ:

```
ws://192.168.1.16:8765/ws
```

- Đèn xanh = WebSocket OK  
- **Reconnect** = mở lại kết nối  
- Demo local: `ws://127.0.0.1:8765/ws` (service `--sim` trên PC)

## Cấu hình

Nút **Cấu hình**:

| Tab | Lưu ở đâu | Ghi chú |
|-----|-----------|---------|
| GCS | `localStorage` trên PC | URL, sidebar, PiP, bản đồ |
| Service / Platform / Camera / Serial / AI / Optics | Jetson `config.yaml` | **Lưu & hot-apply** — không restart process |

Serial quan trọng:

- **VISCA** — zoom ảnh thường FCB (`protocol`, `port`, `baud`, `parity`, `address`)
- **SATIS** — zoom ảnh nhiệt
- **Laser / PTZ / GPS** — đúng cổng UART

## Thành phần UI

- Video chính + PiP + bản đồ  
- Panel PTZ, Camera, AI, Record  
- HUD telemetry (pan/tilt/zoom/LRF/GPS)

Phím tắt: xem [README gốc](../README.md#phím-tắt).
