# Giao thức GCS ↔ Jetson

Vận chuyển: WebSocket `ws://<host>:8765/ws`

- Text frame: JSON (lệnh và telemetry)
- Binary frame: `stream_id (1 byte) + JPEG`

`stream_id`: `0` = ảnh thường, `1` = ảnh nhiệt

## Telemetry (Jetson → GCS), ~15 Hz

```json
{
  "type": "telemetry",
  "ts": 1710000000.123,
  "connected": true,
  "sim": true,
  "pan": 12.4,
  "tilt": -8.1,
  "zoom": 2.0,
  "fov_h": 30.0,
  "fov_v": 17.0,
  "laser_m": 452.3,
  "laser_valid": true,
  "gps": {"lat": 21.0285, "lon": 105.8542, "alt": 18.0, "fix": true},
  "heading": 45.2,
  "camera": {
    "source": "visible",
    "autofocus": true,
    "brightness": 50,
    "contrast": 50,
    "quality": "1080p",
    "fps": 15
  },
  "detect_on": true,
  "track_on": true,
  "track_id": 3,
  "recording": false,
  "detections": [
    {"id": 1, "cls": "person", "conf": 0.91, "x": 0.42, "y": 0.31, "w": 0.08, "h": 0.18}
  ],
  "target_geo": {"lat": 21.031, "lon": 105.86, "alt": 12.0, "valid": true}
}
```

BBox `x,y,w,h` chuẩn hóa 0–1 theo khung hình.

## Lệnh (GCS → Jetson)

```json
{"type": "ptz", "action": "nudge", "pan": 1, "tilt": 0, "speed": 1.0}
{"type": "ptz", "action": "goto", "pan": 20.0, "tilt": -5.0}
{"type": "ptz", "action": "home"}
{"type": "ptz", "action": "stop"}
{"type": "ptz", "action": "slider", "pan": 10.0, "tilt": -2.0}

{"type": "zoom", "action": "in"}
{"type": "zoom", "action": "out"}
{"type": "zoom", "action": "stop"}
{"type": "zoom", "action": "set", "value": 3.5}

{"type": "camera", "autofocus": true, "brightness": 50, "contrast": 50, "quality": "1080p"}
{"type": "view", "main": "visible"}

{"type": "laser", "action": "once"}
{"type": "laser", "action": "continuous", "enabled": true}

{"type": "detect", "enabled": true}
{"type": "track", "action": "click", "x": 0.51, "y": 0.44}
{"type": "track", "action": "roi", "x": 0.2, "y": 0.2, "w": 0.3, "h": 0.3}
{"type": "track", "action": "nearest"}
{"type": "track", "action": "stop"}

{"type": "record", "action": "photo", "save_to": "both"}
{"type": "record", "action": "start"}
{"type": "record", "action": "stop"}

{"type": "config", "action": "get", "requestId": "optional"}
{"type": "config", "action": "set", "persist": true, "requestId": "optional", "config": { "...": "partial hoặc đầy đủ fields như config.yaml" }}
```

Phản hồi config:

```json
{
  "type": "config",
  "ok": true,
  "applied": true,
  "saved": true,
  "path": "config.yaml",
  "config": { },
  "warnings": ["host/port đã lưu; cần restart service để đổi cổng lắng nghe"],
  "requestId": "optional"
}
```

`action: set` ghi `config.yaml` (nếu `persist: true`) rồi **hot-apply**: đóng/mở lại camera, PTZ, laser, SATIS, GPS, AI — không restart process.

## HTTP phụ

- `GET /health`
- `GET /config` — đọc cấu hình hiện tại
- `PUT /config` — body `{ "config": {...}, "persist": true }` (hot-apply)
- `GET /snapshot/visible`
- `GET /snapshot/thermal`
- `GET /recordings` — danh sách file trên Jetson
- `GET /recordings/<name>` — tải file
