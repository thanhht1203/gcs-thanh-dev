from __future__ import annotations

import sys
import threading
import time
from typing import Any

import cv2
import numpy as np

from ..config import CamDevice, Settings
from ..geo import quality_size
from ..sim.world import SimWorld
from ..state import CameraState, Detection


class FrameSource:
    def read(self) -> np.ndarray | None:
        raise NotImplementedError

    def close(self) -> None:
        pass


def _opencv_api(backend: str) -> int | None:
    b = (backend or "auto").lower()
    if b == "dshow":
        return getattr(cv2, "CAP_DSHOW", None)
    if b == "v4l2":
        return getattr(cv2, "CAP_V4L2", None)
    if b == "any":
        return getattr(cv2, "CAP_ANY", 0)
    # auto: Windows + device index → DirectShow (EasyCap)
    if sys.platform.startswith("win"):
        return getattr(cv2, "CAP_DSHOW", None)
    return None


class OpenCvSource(FrameSource):
    def __init__(self, cfg: CamDevice):
        self.cfg = cfg
        self.fallback_w = cfg.width
        self.fallback_h = cfg.height
        self.cap = None
        src: Any = cfg.rtsp if cfg.rtsp else cfg.device
        api = None if cfg.rtsp else _opencv_api(cfg.backend)
        if api is not None and not cfg.rtsp:
            self.cap = cv2.VideoCapture(src, api)
        else:
            self.cap = cv2.VideoCapture(src)
        if self.cap is not None and self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)
            self.cap.set(cv2.CAP_PROP_FPS, cfg.fps)
            print(f"[camera] opened {src} backend={cfg.backend}")
        else:
            print(f"[camera] không mở được {src}")

    def read(self) -> np.ndarray | None:
        if self.cap is None or not self.cap.isOpened():
            return None
        ok, frame = self.cap.read()
        return frame if ok else None

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None


class CameraHub:
    def __init__(self, settings: Settings, world: SimWorld | None, webcam: bool = False):
        self.settings = settings
        self.world = world
        self.webcam = webcam
        self._lock = threading.Lock()
        self.visible: np.ndarray | None = None
        self.thermal: np.ndarray | None = None
        self.sim_dets: list[Detection] = []
        self._vis_src: FrameSource | None = None
        self._th_src: FrameSource | None = None
        self._last = time.perf_counter()
        if not settings.sim:
            self._vis_src = OpenCvSource(settings.cameras.visible)
            self._th_src = OpenCvSource(settings.cameras.thermal)
        elif webcam:
            self._vis_src = OpenCvSource(settings.cameras.visible)

    def _blank(self, w: int, h: int, label: str) -> np.ndarray:
        img = np.zeros((h, w, 3), np.uint8)
        cv2.putText(img, label, (20, h // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 180, 255), 2)
        return img

    def capture(
        self,
        pan: float,
        tilt: float,
        heading: float,
        fov_h: float,
        cam: CameraState,
    ) -> None:
        vw, vh = quality_size(cam.quality, (self.settings.cameras.visible.width, self.settings.cameras.visible.height))
        tw, th = self.settings.cameras.thermal.width, self.settings.cameras.thermal.height
        now = time.perf_counter()
        dt = max(0.001, now - self._last)
        self._last = now

        vis = None
        therm = None
        dets: list[Detection] = []

        if self.world is not None and (self.settings.sim and not self.webcam):
            self.world.step(dt)
            vis, dets = self.world.render(
                pan, tilt, heading, fov_h, vw, vh, False, cam.brightness, cam.contrast
            )
            therm, _ = self.world.render(
                pan, tilt, heading, fov_h, tw, th, True, cam.brightness, cam.contrast
            )
        else:
            if self._vis_src:
                vis = self._vis_src.read()
            if self._th_src:
                therm = self._th_src.read()
            if vis is not None:
                vis = cv2.resize(vis, (vw, vh))
                vis = cv2.convertScaleAbs(vis, alpha=max(0.3, cam.contrast / 50.0), beta=int((cam.brightness - 50) * 1.4))
            if therm is not None:
                therm = cv2.resize(therm, (tw, th))
                if self.settings.cameras.thermal.colormap:
                    gray = cv2.cvtColor(therm, cv2.COLOR_BGR2GRAY) if therm.ndim == 3 else therm
                    therm = cv2.applyColorMap(gray, cv2.COLORMAP_INFERNO)
                elif therm.ndim == 2:
                    therm = cv2.cvtColor(therm, cv2.COLOR_GRAY2BGR)

        if vis is None:
            vis = self._blank(vw, vh, "NO VISIBLE CAMERA")
        if therm is None:
            therm = self._blank(tw, th, "NO THERMAL / EASYCAP")

        with self._lock:
            self.visible = vis
            self.thermal = therm
            self.sim_dets = dets

    def get_visible(self) -> np.ndarray:
        with self._lock:
            if self.visible is None:
                return self._blank(1280, 720, "NO FRAME")
            return self.visible.copy()

    def get_thermal(self) -> np.ndarray:
        with self._lock:
            if self.thermal is None:
                return self._blank(640, 512, "NO FRAME")
            return self.thermal.copy()

    def close(self) -> None:
        if self._vis_src:
            self._vis_src.close()
            self._vis_src = None
        if self._th_src:
            self._th_src.close()
            self._th_src = None

    def reconfigure(self, settings: Settings, webcam: bool | None = None) -> None:
        """Đóng và mở lại camera theo config mới (hot-apply)."""
        if webcam is not None:
            self.webcam = webcam
        self.close()
        self.settings = settings
        if not settings.sim:
            self._vis_src = OpenCvSource(settings.cameras.visible)
            self._th_src = OpenCvSource(settings.cameras.thermal)
        elif self.webcam:
            self._vis_src = OpenCvSource(settings.cameras.visible)
