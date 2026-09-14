from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Detection:
    id: int
    cls: str
    conf: float
    x: float
    y: float
    w: float
    h: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GpsFix:
    lat: float = 0.0
    lon: float = 0.0
    alt: float = 0.0
    fix: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TargetGeo:
    lat: float = 0.0
    lon: float = 0.0
    alt: float = 0.0
    valid: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CameraState:
    source: str = "visible"
    autofocus: bool = True
    brightness: int = 50
    contrast: int = 50
    quality: str = "720p"
    fps: int = 15

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SystemState:
    sim: bool = False
    pan: float = 0.0
    tilt: float = 0.0
    zoom: float = 1.0
    fov_h: float = 60.0
    fov_v: float = 34.0
    laser_m: float = 0.0
    laser_valid: bool = False
    laser_continuous: bool = True
    gps: GpsFix = field(default_factory=GpsFix)
    heading: float = 0.0
    camera: CameraState = field(default_factory=CameraState)
    detect_on: bool = True
    track_on: bool = False
    track_id: int | None = None
    roi: tuple[float, float, float, float] | None = None  # x,y,w,h norm
    recording: bool = False
    detections: list[Detection] = field(default_factory=list)
    target_geo: TargetGeo = field(default_factory=TargetGeo)
    last_photo: str | None = None

    def telemetry(self) -> dict[str, Any]:
        return {
            "type": "telemetry",
            "sim": self.sim,
            "pan": round(self.pan, 2),
            "tilt": round(self.tilt, 2),
            "zoom": round(self.zoom, 2),
            "fov_h": round(self.fov_h, 2),
            "fov_v": round(self.fov_v, 2),
            "laser_m": round(self.laser_m, 1) if self.laser_valid else None,
            "laser_valid": self.laser_valid,
            "gps": self.gps.to_dict(),
            "heading": round(self.heading, 1),
            "camera": self.camera.to_dict(),
            "detect_on": self.detect_on,
            "track_on": self.track_on,
            "track_id": self.track_id,
            "roi": list(self.roi) if self.roi else None,
            "recording": self.recording,
            "detections": [d.to_dict() for d in self.detections],
            "target_geo": self.target_geo.to_dict(),
            "last_photo": self.last_photo,
        }
