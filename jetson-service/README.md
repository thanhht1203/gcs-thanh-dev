# Jetson service (Orin Nano 8GB)

Dịch vụ onboard: camera, PTZ, laser LRF 7047, zoom VISCA (FCB) / SATIS, GPS, YOLO, bám mục tiêu, WebSocket.

Tài liệu tổng: [README gốc](../README.md) · giao thức [protocol.md](../protocol.md)

---

## Chạy nhanh

### Giả lập trên PC

```bash
cd jetson-service
pip install -r requirements.txt
python -m eos_service --sim
```

`--webcam` dùng webcam thay cảnh synthetic.

### Phần cứng

| File | Khi nào |
|------|---------|
| `config.yaml` | **Jetson** — V4L2 + `/dev/ttyUSB*` |
| `config.windows.yaml` | Lab Windows — DirectShow + COM |

```bash
# Jetson
python -m eos_service --config config.yaml

# Windows lab
python -m eos_service --config config.windows.yaml
```

---

## Map thiết bị (Jetson mặc định)

| Thiết bị | Cổng | Protocol |
|----------|------|----------|
| Ảnh thường FCB-EV9520L | `/dev/video0` | V4L2 |
| Zoom VISCA (FCB) | `/dev/ttyUSB0` | VISCA 9600 8N1, `address: 1` |
| Ảnh nhiệt SATIS | `/dev/video1` | V4L2 |
| Zoom SATIS | `/dev/ttyUSB1` | RS422 9600 8E1 |
| Laser LRF 7047 | `/dev/ttyUSB2` | 57600 8E1 |
| Pan-tilt | `/dev/ttyUSB3` | Pelco-D |
| GPS | `/dev/ttyUSB4` | NMEA |

`/dev/video*` = hình ảnh · `/dev/ttyUSB*` = lệnh serial. Thứ tự USB phụ thuộc lúc cắm — chỉnh qua **GCS → Cấu hình** (hot-apply) hoặc sửa `config.yaml`.

Ví dụ VISCA / SATIS trong config (cùng kiểu laser/ptz):

```yaml
visca:
  protocol: visca   # visca | sim
  port: /dev/ttyUSB0
  baud: 9600
  parity: none
  address: 1
  zoom_pulse_s: 0.35

satis:
  protocol: satis   # satis | sim
  port: /dev/ttyUSB1
  baud: 9600
  parity: even
  zoom_speed: 0.5
  fov_set_point: 0.10
  zoom_pulse_s: 0.35
```

---

## Test từng module

```bash
sudo systemctl stop eo-service
cd ~/eo-control/jetson-service   # hoặc đường dẫn repo của bạn
source .venv/bin/activate
```

| Lệnh | Việc làm |
|------|----------|
| `python -m eos_service.hw_test ports` | Liệt kê video + serial |
| `python -m eos_service.hw_test cameras` | Đọc 1 frame |
| `python -m eos_service.hw_test cameras --preview` | **Cửa sổ video** (`q` thoát) |
| `python -m eos_service.hw_test cameras --snapshot` | Lưu JPG `data/hw_test/` |
| `python -m eos_service.hw_test visca` | Zoom FCB |
| `python -m eos_service.hw_test satis` | Zoom SATIS |
| `python -m eos_service.hw_test laser` | Đo LRF |
| `python -m eos_service.hw_test ptz` | Nudge PTZ |
| `python -m eos_service.hw_test gps` | GPS fix |
| `python -m eos_service.hw_test` | Tất cả |

```bash
sudo systemctl start eo-service
```

---

## YOLO / TensorRT

```bash
pip install -r requirements-jetson.txt
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
```

```bash
yolo export model=yolov8n.pt format=engine device=0
# ai.model: yolov8n.engine trong config.yaml
```

---

## systemd

Mẫu: [`systemd/eo-service.service`](systemd/eo-service.service).

```bash
sudo systemctl enable --now eo-service
sudo journalctl -u eo-service -f
```

Deploy từ PC: `deploy-jetson.bat` (xem README gốc).
