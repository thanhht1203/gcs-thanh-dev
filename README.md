# EO Control System

Hệ thống điều khiển điện quang: **ảnh thường** + **ảnh nhiệt** + **laser đo xa** + **pan-tilt** + **AI phát hiện/bám mục tiêu**.

Gồm 2 phần:

| Phần | Thư mục | Chạy trên |
|------|---------|-----------|
| **GCS** | [`gcs/`](gcs/) | Windows PC (Electron + React) |
| **Jetson service** | [`jetson-service/`](jetson-service/) | Jetson Orin Nano 8GB (Python / FastAPI) |

Tài liệu chi tiết từng phần: [gcs/README.md](gcs/README.md) · [jetson-service/README.md](jetson-service/README.md) · [protocol.md](protocol.md)

---

## Kiến trúc

```
┌─────────────────────────────┐     WebSocket JSON + JPEG      ┌──────────────────────────────┐
│  GCS (Electron)             │ ◄────────────────────────────► │  Jetson Orin Nano            │
│  - Video visible / thermal  │   lệnh PTZ, zoom, bám, ghi    │  - Camera FCB + SATIS        │
│  - PTZ, zoom, HUD, bản đồ   │   telemetry: góc, GPS, AI     │  - VISCA / SATIS / LRF / PTZ │
│  - Panel Cấu hình           │   ws://<IP>:8765/ws           │  - YOLO + bám mục tiêu       │
└─────────────────────────────┘                                └──────────────────────────────┘
```

- **Ảnh thường (FCB-EV9520L):** video `/dev/video0` + zoom **VISCA** qua UART (`/dev/ttyUSB*`)
- **Ảnh nhiệt (SATIS):** video `/dev/video1` + zoom **SATIS** RS422
- Zoom trên GCS: màn ảnh thường → VISCA; màn ảnh nhiệt → SATIS

Chế độ `--sim` chạy service trên PC (không cần Jetson/phần cứng) để làm UI và demo.

---

## Cấu trúc repo

```
gcs-thanh/
├── gcs/                    # Giao diện Windows
├── jetson-service/         # Service onboard
│   ├── config.yaml         # Mặc định Jetson (V4L2 + ttyUSB)
│   ├── config.windows.yaml # Lab Windows (DirectShow + COM)
│   ├── eos_service/        # Mã nguồn service
│   └── systemd/            # Unit eo-service
├── scripts/deploy-jetson.py
├── deploy-jetson.bat
├── protocol.md             # Giao thức GCS ↔ Jetson
└── start-sim.bat           # Demo sim trên Windows
```

---

## Chạy demo trên Windows (sim)

Cần **Python 3.10+** và **Node.js 18+**.

```bat
REM Cửa sổ 1 — service giả lập
cd jetson-service
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m eos_service --sim

REM Cửa sổ 2 — GCS
cd gcs
npm install
npm run electron:dev
```

Hoặc `start-sim.bat` ở thư mục gốc.

Kết nối: `ws://127.0.0.1:8765/ws`

---

## Cài và chạy trên Jetson

### Lần đầu

```bash
# Trên Jetson (ví dụ user thanh)
mkdir -p ~/eo-control
# Copy code từ PC bằng deploy-jetson.bat (khuyến nghị) hoặc scp/git

cd ~/eo-control/jetson-service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# AI YOLOv8n (Orin Nano)
pip install -r requirements-jetson.txt
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
# hoặc từ PC: py -3 scripts/setup-jetson-ai.py  /  py -3 scripts/deploy-jetson.py --ai

# Sửa config.yaml cho đúng cổng video/UART (sim: false)
python -m eos_service --config config.yaml
```

### systemd (khởi động cùng máy)

```bash
sudo cp systemd/eo-service.service /etc/systemd/system/
# Sửa User= / WorkingDirectory= / ExecStart= cho đúng đường dẫn
sudo systemctl daemon-reload
sudo systemctl enable --now eo-service
sudo systemctl status eo-service
```

Health check từ PC:

```bat
curl http://192.168.1.16:8765/health
```

GCS trỏ tới: `ws://192.168.1.16:8765/ws`

---

## Cập nhật code lên Jetson

Từ PC (Windows), thư mục gốc repo:

```bat
deploy-jetson.bat
```

Hoặc:

```bat
set JETSON_HOST=192.168.1.16
set JETSON_USER=thanh
set JETSON_PASSWORD=your_password
py -3 scripts\deploy-jetson.py
```

| Cờ | Ý nghĩa |
|----|---------|
| *(mặc định)* | Copy code, **không** ghi đè `config.yaml` trên Jetson, restart service |
| `--deps` | `pip install -r requirements.txt` lại |
| `--include-config` | Ghi đè luôn `config.yaml` |
| `--sim` | Unit chạy với `--sim` |
| `--no-restart` | Chỉ copy file |

SSH key (khuyến nghị, khỏi nhập mật khẩu mỗi lần):

```bat
ssh-keygen -t ed25519 -N "" -f %USERPROFILE%\.ssh\id_ed25519
type %USERPROFILE%\.ssh\id_ed25519.pub | ssh thanh@192.168.1.16 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

---

## Phần cứng & config

Hai file mẫu:

| File | Khi nào dùng |
|------|----------------|
| `jetson-service/config.yaml` | Jetson thật — V4L2 + `/dev/ttyUSB*` |
| `jetson-service/config.windows.yaml` | Lab Windows — DirectShow + `COMx` |

Map mặc định trên Jetson:

| Thiết bị | Video / UART | Protocol |
|----------|--------------|----------|
| Ảnh thường FCB-EV9520L | `/dev/video0` | V4L2 |
| Zoom VISCA (FCB) | `/dev/ttyUSB0` | VISCA 9600 8N1, `address: 1` |
| Ảnh nhiệt SATIS | `/dev/video1` | V4L2 |
| Zoom SATIS | `/dev/ttyUSB1` | RS422 9600 8E1 |
| Laser LRF 7047 | `/dev/ttyUSB2` | 57600 8E1 |
| Pan-tilt | `/dev/ttyUSB3` | Pelco-D |
| GPS | `/dev/ttyUSB4` | NMEA |

**Lưu ý:** `/dev/video*` = luồng hình; `/dev/ttyUSB*` = lệnh serial (zoom/PTZ/laser). Không trộn hai loại cổng. Thứ tự `ttyUSB*` phụ thuộc lúc cắm USB.

### Cấu hình trên GCS

Nút **Cấu hình** trên thanh trên:

- **Tab GCS:** URL WebSocket, layout (sidebar, PiP, bản đồ) — lưu `localStorage` trên PC
- **Tab Service / Camera / Serial / AI…:** chỉnh `config.yaml` trên Jetson → **Lưu & hot-apply** (mở lại thiết bị, không restart process)
- Đổi `host`/`port` lắng nghe: cần `systemctl restart eo-service`

Nút **Reconnect** nếu báo mất kết nối.

---

## Test từng module phần cứng

Tạm dừng service (tránh chiếm camera/serial), rồi chạy trên Jetson:

```bash
sudo systemctl stop eo-service
cd ~/eo-control/jetson-service
source .venv/bin/activate
```

| Lệnh | Việc làm |
|------|----------|
| `python -m eos_service.hw_test ports` | Liệt kê `/dev/video*` + `ttyUSB*` |
| `python -m eos_service.hw_test cameras` | Đọc 1 frame mỗi camera |
| `python -m eos_service.hw_test cameras --preview` | **Mở cửa sổ video** (`q` thoát) |
| `python -m eos_service.hw_test cameras --snapshot` | Lưu JPG → `data/hw_test/` |
| `python -m eos_service.hw_test visca` | Zoom IN/OUT/STOP FCB |
| `python -m eos_service.hw_test satis` | Zoom SATIS |
| `python -m eos_service.hw_test laser` | Đo 1 phát LRF |
| `python -m eos_service.hw_test ptz` | Nudge pan/tilt |
| `python -m eos_service.hw_test gps` | Chờ GPS fix |
| `python -m eos_service.hw_test` | Chạy tất cả |

SSH không GUI → dùng `--snapshot` rồi `scp` về PC. Xong:

```bash
sudo systemctl start eo-service
```

---

## Chức năng GCS

| Nhóm | Nội dung |
|------|----------|
| Camera | Ảnh thường / nhiệt, zoom, sáng/tương phản, chất lượng |
| PTZ | WASD / mũi tên, nút màn hình, Home, góc, thanh trượt |
| Laser | Đo xa, hiển thị khoảng cách |
| AI | Phát hiện (YOLO), bám (click / ROI / gần tâm) |
| Media | Chụp ảnh, quay video |
| Bản đồ | Vị trí thiết bị + tọa độ mục tiêu |

### Phím tắt

| Phím | Chức năng |
|------|-----------|
| W/S · ↑↓ | Tilt |
| A/D · ←→ | Pan |
| +/- | Zoom |
| H | Home |
| Space | Chụp ảnh |
| R | Quay video on/off |
| T | Bám gần tâm |
| G | Phát hiện on/off |
| 1 / 2 | Ảnh thường / nhiệt làm màn chính |
| Esc | Dừng bám / xóa ROI |

Chuột: click = chọn mục tiêu; kéo = khoanh ROI (bbox theo mục tiêu khi đang bám).

---

## Giao thức

Xem [protocol.md](protocol.md): WebSocket `ws://<host>:8765/ws`, JSON lệnh/telemetry, binary JPEG (`stream_id` 0=visible, 1=thermal).

HTTP phụ: `GET /health`, `GET/PUT /config`, `GET /snapshot/visible|thermal`, `GET /recordings`.

---

## Xử lý sự cố nhanh

| Hiện tượng | Gợi ý |
|------------|--------|
| GCS **Mất kết nối** | Kiểm tra `curl http://<IP>:8765/health`; bấm **Reconnect**; URL đúng `ws://<IP>:8765/ws` |
| Camera đen / NO FRAME | `hw_test ports` + `cameras --preview`; đúng `device`/`backend` trong config |
| Zoom không chạy | Đúng `visca.port` / `satis.port` (UART, không phải `/dev/video*`); `hw_test visca` / `satis` |
| Serial fail → sim | Cổng đang bị `eo-service` chiếm — `systemctl stop` trước khi test |
| AI không detect | `py -3 scripts/setup-jetson-ai.py`; health `ai_ok:true`; `hw_test ai`; GCS panel hiện YOLO |
