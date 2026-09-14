from __future__ import annotations

import math
import time
from dataclasses import dataclass

import cv2
import numpy as np

from ..state import Detection


@dataclass
class SimObject:
    oid: int
    cls: str
    east: float
    north: float
    height: float
    width: float
    speed_e: float
    speed_n: float
    hot: float  # 0-1 thermal signature


class SimWorld:
    """Môi trường giả lập: mặt đất + người/xe, chiếu qua camera gimbal."""

    def __init__(self, height_m: float = 12.0, seed: int = 7):
        self.height_m = height_m
        rng = np.random.default_rng(seed)
        self.objects: list[SimObject] = []
        oid = 1
        for _ in range(5):
            self.objects.append(
                SimObject(
                    oid=oid,
                    cls="person",
                    east=float(rng.uniform(-80, 80)),
                    north=float(rng.uniform(20, 160)),
                    height=1.7,
                    width=0.6,
                    speed_e=float(rng.uniform(-1.2, 1.2)),
                    speed_n=float(rng.uniform(-0.8, 0.8)),
                    hot=0.9,
                )
            )
            oid += 1
        for cls in ("car", "truck", "motorcycle"):
            self.objects.append(
                SimObject(
                    oid=oid,
                    cls=cls,
                    east=float(rng.uniform(-120, 120)),
                    north=float(rng.uniform(40, 220)),
                    height=1.6 if cls != "truck" else 3.2,
                    width=4.2 if cls == "car" else (7.5 if cls == "truck" else 2.0),
                    speed_e=float(rng.uniform(-8, 8)),
                    speed_n=float(rng.uniform(-2, 2)),
                    hot=0.55,
                )
            )
            oid += 1
        self._t0 = time.perf_counter()

    def step(self, dt: float) -> None:
        for o in self.objects:
            o.east += o.speed_e * dt
            o.north += o.speed_n * dt
            if abs(o.east) > 180:
                o.speed_e *= -1
            if o.north < 10 or o.north > 260:
                o.speed_n *= -1

    def _project(
        self,
        east: float,
        north: float,
        up: float,
        pan: float,
        tilt: float,
        heading: float,
        fov_h: float,
        w: int,
        h: int,
    ) -> tuple[float, float, float] | None:
        # World ENU relative to camera at origin, camera height already in `up` of objects vs camera.
        az = math.radians(heading + pan)
        el = math.radians(tilt)
        # Rotate world into camera frame: yaw then pitch. Camera looks along +north initially.
        # First apply yaw (heading+pan) around up
        e1 = east * math.cos(az) - north * math.sin(az)
        n1 = east * math.sin(az) + north * math.cos(az)
        u1 = up
        # Pitch (tilt): rotate around camera-right (east axis)
        n2 = n1 * math.cos(el) + u1 * math.sin(el)
        u2 = -n1 * math.sin(el) + u1 * math.cos(el)
        e2 = e1
        if n2 <= 0.5:
            return None
        fov_v = 2 * math.atan(math.tan(math.radians(fov_h) / 2) * (h / max(w, 1)))
        xf = e2 / (n2 * math.tan(math.radians(fov_h) / 2))
        yf = -u2 / (n2 * math.tan(fov_v / 2))
        u = (xf + 1) * 0.5 * w
        v = (yf + 1) * 0.5 * h
        return u, v, n2

    def render(
        self,
        pan: float,
        tilt: float,
        heading: float,
        fov_h: float,
        width: int,
        height: int,
        thermal: bool = False,
        brightness: int = 50,
        contrast: int = 50,
    ) -> tuple[np.ndarray, list[Detection]]:
        t = time.perf_counter() - self._t0
        if thermal:
            base = np.zeros((height, width, 3), np.uint8)
            yy = np.linspace(0, 1, height)[:, None]
            cool = (40 + 30 * yy).astype(np.uint8)
            base[:, :, 0] = cool
            base[:, :, 1] = (20 + 10 * yy).astype(np.uint8)
            base[:, :, 2] = (cool * 0.4).astype(np.uint8)
        else:
            sky = np.zeros((height, width, 3), np.uint8)
            for i in range(height):
                k = i / max(height - 1, 1)
                sky[i, :, 0] = int(40 + 30 * k)
                sky[i, :, 1] = int(70 + 50 * k)
                sky[i, :, 2] = int(90 + 40 * (1 - k))
            base = sky
            horizon = int(height * (0.45 - tilt / 90.0 * 0.25))
            horizon = max(0, min(height - 1, horizon))
            ground = base[horizon:].copy()
            # grid on ground
            for g in range(0, width, 40):
                shift = int((pan * 3 + t * 8) % 40)
                x = (g + shift) % width
                cv2.line(ground, (x, 0), (x // 2 + width // 4, ground.shape[0] - 1), (38, 70, 42), 1)
            base[horizon:] = cv2.addWeighted(base[horizon:], 0.35, ground, 0.65, 0)
            cv2.line(base, (0, horizon), (width, horizon), (90, 110, 80), 1)

        detections: list[Detection] = []
        cam_up = self.height_m
        for o in self.objects:
            pts = []
            corners = [
                (o.east - o.width / 2, o.north, 0.0),
                (o.east + o.width / 2, o.north, 0.0),
                (o.east - o.width / 2, o.north, o.height),
                (o.east + o.width / 2, o.north, o.height),
            ]
            for e, n, z in corners:
                p = self._project(e, n, z - cam_up, pan, tilt, heading, fov_h, width, height)
                if p:
                    pts.append(p)
            if len(pts) < 3:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            dist = float(np.mean([p[2] for p in pts]))
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            if x2 < 0 or y2 < 0 or x1 >= width or y1 >= height:
                continue
            x1c, y1c = int(max(0, x1)), int(max(0, y1))
            x2c, y2c = int(min(width - 1, x2)), int(min(height - 1, y2))
            if x2c - x1c < 2 or y2c - y1c < 2:
                continue
            if thermal:
                heat = int(80 + o.hot * 175)
                color = (heat // 4, heat // 2, heat)
            else:
                color = {
                    "person": (60, 200, 255),
                    "car": (40, 80, 180),
                    "truck": (30, 50, 120),
                    "motorcycle": (20, 140, 90),
                }.get(o.cls, (200, 200, 200))
            cv2.rectangle(base, (x1c, y1c), (x2c, y2c), color, -1)
            if o.cls == "person":
                head_y = y1c + max(2, (y2c - y1c) // 5)
                cv2.circle(base, ((x1c + x2c) // 2, head_y), max(2, (x2c - x1c) // 3), (40, 40, 40), -1)
            else:
                cv2.rectangle(
                    base,
                    (x1c + 2, y1c + 2),
                    (x2c - 2, y1c + max(4, (y2c - y1c) // 3)),
                    (min(255, color[0] + 40),) * 3,
                    -1,
                )
            nx = x1c / width
            ny = y1c / height
            nw = (x2c - x1c) / width
            nh = (y2c - y1c) / height
            # confidence falls with distance / tiny boxes
            conf = float(np.clip(0.98 - dist / 500.0, 0.45, 0.98))
            detections.append(Detection(id=o.oid, cls=o.cls, conf=conf, x=nx, y=ny, w=nw, h=nh))

        # brightness / contrast
        alpha = max(0.3, min(2.5, contrast / 50.0))
        beta = int((brightness - 50) * 1.4)
        base = cv2.convertScaleAbs(base, alpha=alpha, beta=beta)

        # mild noise
        noise = np.random.normal(0, 4 if not thermal else 8, base.shape).astype(np.int16)
        base = np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        if thermal:
            gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
            base = cv2.applyColorMap(gray, cv2.COLORMAP_INFERNO)

        # HUD-ish grain
        cv2.putText(
            base,
            "SIM EO" if not thermal else "SIM IR",
            (12, height - 16),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (180, 220, 180) if not thermal else (180, 220, 255),
            1,
            cv2.LINE_AA,
        )
        return base, detections
