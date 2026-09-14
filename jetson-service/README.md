# Jetson service (Orin Nano 8GB)

Dịch vụ onboard: camera, PTZ, laser LRF 7047, SATIS zoom, GPS, YOLO, bám mục tiêu, WebSocket.

## Giả lập trên PC

```bash
pip install -r requirements.txt
python -m eos_service --sim
```

`--webcam` dùng webcam thay vì cảnh synthetic.

## Phần cứng thật (Windows / Jetson)

Sửa `config.yaml` theo cổng máy bạn (mẫu đã map theo code LRF/SATIS):

| Thiết bị | config.yaml | Protocol |
|----------|-------------|----------|
| Ảnh thường | `cameras.visible.device` | V4L2 / CSI / DSHOW |
| Ảnh nhiệt SATIS | `cameras.thermal` + EasyCap | `backend: dshow`, `colormap: false` |
| Zoom SATIS | `satis.port` (VD `COM25`) | RS422 9600 8E1, TR_IN_OP_FOV |
| Laser LRF 7047 | `laser.port` (VD `COM26`) | 57600 8E1, `>LM,Md,3*CS` |
| Pan-tilt | `ptz.port` | Pelco-D RS-485 |
| GPS | `gps.port` | NMEA GGA/RMC |
| Compass | `compass.source: gps` hoặc serial HDT | |

Nếu không mở được serial, service tự chuyển kênh đó sang sim.

```bash
python -m eos_service --config config.yaml
```

Trên Jetson đổi `COM25`/`COM26` → `/dev/ttyUSBx`.

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

## systemd

Copy `systemd/eo-service.service` tới `/etc/systemd/system/`, sửa User/WorkingDirectory, rồi:

```bash
sudo systemctl enable --now eo-service
```
