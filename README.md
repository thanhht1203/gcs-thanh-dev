# EO Control System

Hệ thống điều khiển điện quang (ảnh thường + ảnh nhiệt + đo xa laser + pan-tilt) gồm:

1. **GCS Windows** — phần mềm giao diện điều khiển trên PC
2. **Jetson service** — dịch vụ trên Jetson Orin Nano 8GB (camera, cảm biến, AI phát hiện/bám mục tiêu)

Phù hợp bảng nội dung: tích hợp cảm biến (1 tháng) → AI trên Jetson → phần mềm điều khiển PC (2 tháng).

## Kiến trúc

```
┌─────────────────────────────┐          WebSocket + JPEG           ┌──────────────────────────────┐
│  GCS Windows (Electron)     │ ◄─────────────────────────────────► │  Jetson Orin Nano 8GB        │
│  - Video ảnh thường/nhiệt   │     lệnh PTZ, zoom, bám, ghi hình   │  - Camera / thermal / laser   │
│  - PTZ, zoom, HUD           │     telemetry: góc, GPS, detections │  - YOLO + ByteTrack           │
│  - Bản đồ + tọa độ mục tiêu │                                     │  - Pan-tilt, GPS, compass     │
└─────────────────────────────┘                                     └──────────────────────────────┘
```

Chế độ `--sim` chạy service ngay trên Windows (không cần Jetson/phần cứng) để làm giao diện và demo.

## Chức năng

| Nhóm | Nội dung |
|------|----------|
| Camera | Ảnh thường, ảnh nhiệt, zoom, auto focus, sáng/tương phản, Full HD/HD |
| PTZ | Phím mũi tên/WASD, nút màn hình, Home, nhập góc, thanh trượt |
| Laser | Đo xa, hiển thị khoảng cách |
| AI | Phát hiện người/xe (YOLO), bám mục tiêu (ByteTrack / click / khoanh ROI) |
| Media | Chụp ảnh, quay video, lưu trên Jetson hoặc tải về PC |
| Bản đồ | Vị trí thiết bị, tọa độ mục tiêu (GPS + compass + laser + góc gimbal) |

## Chạy demo trên Windows (không cần Jetson)

Cần **Python 3.10+** và **Node.js 18+**.

```bat
REM Cửa sổ 1 — service giả lập
cd jetson-service
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m eos_service --sim

REM Cửa sổ 2 — giao diện GCS
cd gcs
npm install
npm run electron:dev
```

Hoặc chạy `start-sim.bat` ở thư mục gốc.

Kết nối mặc định: `ws://127.0.0.1:8765/ws`

## Chạy trên Jetson Orin Nano 8GB

```bash
cd jetson-service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Tải model YOLO (lần đầu)
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
# Sửa config.yaml cho đúng cổng camera / UART
python -m eos_service --config config.yaml
```

Cài service systemd: xem `jetson-service/systemd/eo-service.service`.

## Cập nhật code lên Jetson

Từ máy GCS (Windows), trong thư mục gốc repo:

```bat
deploy-jetson.bat
```

Hoặc:

```bat
set JETSON_PASSWORD=your_password
py -3 scripts\deploy-jetson.py
```

Script sẽ:
1. Copy `jetson-service/` → `/home/thanh/eo-control/jetson-service` (mặc định **không** ghi đè `config.yaml` trên Jetson)
2. `sudo systemctl restart eo-service`

Tuỳ chọn:

| Cờ | Ý nghĩa |
|----|---------|
| `--deps` | `pip install -r requirements.txt` lại trên Jetson |
| `--include-config` | Ghi đè luôn `config.yaml` |
| `--sim` | Cập nhật unit chạy chế độ sim |
| `--no-restart` | Chỉ copy file, không restart |

Khuyến nghị cấu hình SSH key một lần để khỏi nhập mật khẩu:

```bat
ssh-keygen -t ed25519 -N "" -f %USERPROFILE%\.ssh\id_ed25519
type %USERPROFILE%\.ssh\id_ed25519.pub | ssh thanh@192.168.1.16 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

GCS trên PC trỏ tới IP Jetson, ví dụ `ws://192.168.1.16:8765/ws`.

## Phần cứng (map trong `config.yaml`)

| Thiết bị | Mặc định | Ghi chú |
|----------|----------|---------|
| Camera ảnh thường | `/dev/video0` hoặc CSI | V4L2 / OpenCV |
| Camera nhiệt | `/dev/video1` hoặc RTSP | FLIR/Hikvision UVC hoặc RTSP |
| Laser rangefinder | UART `/dev/ttyUSB0` | Parser generic + LightWare |
| Pan-tilt | Pelco-D RS-485 `/dev/ttyUSB1` | Hoặc protocol `sim` |
| GPS | NMEA `/dev/ttyUSB2` | GGA/RMC |
| Compass | NMEA HDT/HDM hoặc từ GPS | |

## Phím tắt GCS

| Phím | Chức năng |
|------|-----------|
| W/S hoặc ↑↓ | Tilt |
| A/D hoặc ←→ | Pan |
| +/- | Zoom |
| H | Home (pan/tilt = 0) |
| Space | Chụp ảnh |
| R | Bật/tắt quay video |
| T | Bám mục tiêu gần tâm |
| G | Bật/tắt phát hiện |
| 1 / 2 | Ảnh thường / ảnh nhiệt làm màn chính |
| Esc | Dừng bám / xóa ROI |

Chuột: click trên video = chọn mục tiêu bám; kéo = khoanh vùng tìm kiếm.
# gcs-thanh
