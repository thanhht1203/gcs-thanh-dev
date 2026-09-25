from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config.yaml"


class PlatformCfg(BaseModel):
    role: str = "mast"
    height_m: float = 12.0
    default_lat: float = 21.0285
    default_lon: float = 105.8542
    default_alt: float = 18.0
    default_heading: float = 0.0


class CamDevice(BaseModel):
    device: int | str = 0
    width: int = 1280
    height: int = 720
    fps: int = 15
    rtsp: str | None = None
    # auto | dshow | v4l2 | any — EasyCap trên Windows dùng dshow
    backend: str = "auto"
    # MJPG | YUYV | UYVY | để trống = tự thử (FCB capture hay cần MJPG)
    fourcc: str = ""
    # false = giữ nguyên frame (SATIS analog qua EasyCap)
    colormap: bool = True


class CamerasCfg(BaseModel):
    visible: CamDevice = Field(
        default_factory=lambda: CamDevice(
            device="/dev/video0", width=1920, height=1080, fps=60, backend="v4l2", colormap=False
        )
    )
    thermal: CamDevice = Field(
        default_factory=lambda: CamDevice(
            device="/dev/video1", width=640, height=512, backend="v4l2", colormap=False
        )
    )


class PtzCfg(BaseModel):
    protocol: str = "pelco_d"
    port: str = "/dev/ttyUSB3"
    baud: int = 2400
    address: int = 1
    pan_min: float = -180
    pan_max: float = 180
    tilt_min: float = -45
    tilt_max: float = 45
    pan_speed: float = 12.0
    tilt_speed: float = 8.0


class LaserCfg(BaseModel):
    port: str = "/dev/ttyUSB2"
    baud: int = 57600
    protocol: str = "lrf7047"  # lrf7047 | generic | lightware | sim
    parity: str = "even"  # none | even | odd
    measure_cmd: str = "LM,Md,3"
    measure_interval_s: float = 0.8


class SatisCfg(BaseModel):
    """
    SATIS ảnh nhiệt gồm 2 kết nối khác nhau:
      - video: /dev/video*  → OpenCV (V4L2), KHÔNG dùng pyserial
      - port:  /dev/ttyUSB* → RS422 zoom (pyserial)
    """

    protocol: str = "satis"  # satis | sim
    # Tương thích config cũ (enabled: false ≡ protocol: sim)
    enabled: bool = True
    # Stream ảnh nhiệt (EasyCap / USB capture)
    video: str | int | None = "/dev/video1"
    # RS422 điều khiển zoom — chỉ tty/COM, không phải /dev/video*
    port: str = "/dev/ttyUSB1"
    baud: int = 9600
    parity: str = "even"
    zoom_speed: float = 0.5  # 0.3 .. 1.3 s^-1
    fov_set_point: float = 0.10
    zoom_pulse_s: float = 0.35


class ViscaCfg(BaseModel):
    """
    FCB-EV9520L ảnh thường gồm 2 kết nối:
      - video: /dev/video* → OpenCV (V4L2), KHÔNG dùng pyserial
      - port:  /dev/ttyUSB* → VISCA zoom (pyserial)
    """

    protocol: str = "visca"  # visca | sim
    # Giữ enabled để tương thích config cũ (enabled: false ≡ protocol: sim)
    enabled: bool = True
    # Stream ảnh thường (capture card / CSI)
    video: str | int | None = "/dev/video0"
    # VISCA UART — chỉ tty/COM
    port: str = "/dev/ttyUSB0"
    baud: int = 9600
    parity: str = "none"  # none | even | odd — FCB board thường 8N1
    address: int = 1  # VISCA camera address → 0x81
    zoom_pulse_s: float = 0.35


class GpsCfg(BaseModel):
    port: str = "/dev/ttyUSB4"
    baud: int = 9600


class CompassCfg(BaseModel):
    source: str = "gps"
    port: str = "/dev/ttyUSB5"
    baud: int = 9600


class AiCfg(BaseModel):
    model: str = "yolov8n.pt"
    device: int | str = 0
    conf: float = 0.4
    imgsz: int = 640
    classes: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 5, 7])
    use_ultralytics: bool = True


class OpticsCfg(BaseModel):
    fov_h_1x: float = 60.0
    zoom_min: float = 1.0
    zoom_max: float = 30.0


class RecordCfg(BaseModel):
    dir: str = "data/recordings"
    fourcc: str = "mp4v"


class Settings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8765
    sim: bool = False
    platform: PlatformCfg = Field(default_factory=PlatformCfg)
    cameras: CamerasCfg = Field(default_factory=CamerasCfg)
    ptz: PtzCfg = Field(default_factory=PtzCfg)
    laser: LaserCfg = Field(default_factory=LaserCfg)
    satis: SatisCfg = Field(default_factory=SatisCfg)
    visca: ViscaCfg = Field(default_factory=ViscaCfg)
    gps: GpsCfg = Field(default_factory=GpsCfg)
    compass: CompassCfg = Field(default_factory=CompassCfg)
    ai: AiCfg = Field(default_factory=AiCfg)
    optics: OpticsCfg = Field(default_factory=OpticsCfg)
    record: RecordCfg = Field(default_factory=RecordCfg)


def load_settings(path: str | None = None, sim_override: bool | None = None) -> Settings:
    cfg_path = Path(path) if path else DEFAULT_CONFIG
    data: dict[str, Any] = {}
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    settings = Settings.model_validate(data)
    if sim_override is not None:
        settings.sim = sim_override
    if os.environ.get("EOS_SIM") == "1":
        settings.sim = True
    settings.record.dir = str(_resolve_record_dir(settings.record.dir))
    return settings


def _resolve_record_dir(dir_path: str) -> Path:
    rec = Path(dir_path)
    if not rec.is_absolute():
        rec = ROOT / rec
    rec.mkdir(parents=True, exist_ok=True)
    return rec


def settings_to_dict(settings: Settings) -> dict[str, Any]:
    """Xuất dict để gửi GCS / ghi YAML (record.dir ưu tiên relative nếu nằm trong ROOT)."""
    data = settings.model_dump(mode="python")
    rec = Path(str(data.get("record", {}).get("dir", "data/recordings")))
    try:
        if rec.is_absolute():
            data["record"]["dir"] = str(rec.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        data["record"]["dir"] = str(rec).replace("\\", "/")
    return data


def save_settings(settings: Settings, path: str | Path) -> Path:
    cfg_path = Path(path)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    data = settings_to_dict(settings)
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return cfg_path


def merge_settings(base: Settings, patch: dict[str, Any]) -> Settings:
    """Deep-merge patch dict vào Settings hiện tại."""
    current = settings_to_dict(base)
    _deep_merge(current, patch)
    merged = Settings.model_validate(current)
    merged.record.dir = str(_resolve_record_dir(merged.record.dir))
    return merged


def _deep_merge(dst: dict[str, Any], src: dict[str, Any]) -> None:
    for key, val in src.items():
        if isinstance(val, dict) and isinstance(dst.get(key), dict):
            _deep_merge(dst[key], val)
        else:
            dst[key] = val


def parse_cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="EO Control Jetson service")
    p.add_argument("--config", default=str(DEFAULT_CONFIG))
    p.add_argument("--sim", action="store_true", help="Chạy giả lập (không cần phần cứng)")
    p.add_argument("--host", default=None)
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--webcam", action="store_true", help="Dùng webcam thật trong chế độ sim")
    return p.parse_args()
