# Jetson service (Orin Nano 8GB)

Dịch vụ onboard: camera, PTZ, laser LRF 7047, VISCA/SATIS zoom, GPS, YOLO, bám mục tiêu, WebSocket.

## Giả lập trên PC

```bash
pip install -r requirements.txt
python -m eos_service --sim
```

`--webcam` dùng webcam thay vì cảnh synthetic.

## Phần cứng

| File | Dùng khi |
|------|----------|
| `config.yaml` | **Mặc định Jetson** — V4L2 + `/dev/ttyUSB*` |
| `config.windows.yaml` | Lab Windows — DirectShow + COM |

```bash
# Jetson
python -m eos_service --config config.yaml

# Windows lab
python -m eos_service --config config.windows.yaml
```

| Thiết bị | Jetson (mặc định) | Protocol |
|----------|-------------------|----------|
| Ảnh thường FCB | video `0`, `v4l2` | V4L2 |
| Zoom VISCA | `/dev/ttyUSB0` | 9600 8N1 |
| Ảnh nhiệt SATIS | video `1`, `v4l2` | V4L2 |
| Zoom SATIS | `/dev/ttyUSB1` | RS422 9600 8E1 |
| Laser LRF 7047 | `/dev/ttyUSB2` | 57600 8E1 |
| Pan-tilt | `/dev/ttyUSB3` | Pelco-D |
| GPS | `/dev/ttyUSB4` | NMEA |

Thứ tự `ttyUSB*` phụ thuộc lúc cắm USB. Chỉnh từ **GCS → Cấu hình → Camera / Serial → Lưu & hot-apply** (ghi `config.yaml` + mở lại cổng, không cần restart process). Đổi `host`/`port` vẫn cần restart service.

Nếu không mở được serial/camera, kênh đó tự chuyển sim.

## Jetson + YOLO

```bash
pip install -r requirements-jetson.txt
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
python -m eos_service --config config.yaml
```

TensorRT (tùy chọn):

```bash
yolo export model=yolov8n.pt format=engine device=0
# rồi đặt ai.model: yolov8n.engine trong config.yaml
```

## Cập nhật code từ PC

```bat
REM Từ thư mục gốc repo trên Windows
deploy-jetson.bat
```

Chi tiết: xem README gốc (`../README.md` mục "Cập nhật code lên Jetson").
