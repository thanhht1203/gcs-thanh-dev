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
    if sys.platform.startswith("win"):
        return getattr(cv2, "CAP_DSHOW", None)
    return None


def _device_disabled(device: Any) -> bool:
    if device is None:
        return True
    s = str(device).strip().lower()
    return s in ("", "none", "null", "off", "-1")


def _fourcc_plan(cfg: CamDevice) -> list[str]:
    """Thu MJPG truoc (HDMI/USB capture FCB), roi YUYV. Cam da co frame thi khong doi."""
    preferred = (cfg.fourcc or "").strip().upper()
    order = ["MJPG", "YUYV", "UYVY", ""]
    if preferred and preferred not in ("AUTO", "ANY"):
        order = [preferred] + [x for x in order if x != preferred]
    # bo trung
    seen: set[str] = set()
    out: list[str] = []
    for item in order:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


class OpenCvSource(FrameSource):
    """
    Doc camera o thread rieng.

    Neu 1 cam (/dev/video0) bi V4L2 select() timeout, khong lam treo cam kia.
    FCB capture thu lai MJPG/YUYV vi mo duoc nhung khong co frame khi sai pixel format.
    """

    def __init__(self, cfg: CamDevice, name: str = "camera"):
        self.cfg = cfg
        self.name = name
        self.fallback_w = cfg.width
        self.fallback_h = cfg.height
        self.cap = None
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._fail_count = 0
        self._opened = False
        self._got_frame = False
        self._src: Any = cfg.rtsp if cfg.rtsp else cfg.device
        self._api = None if cfg.rtsp else _opencv_api(cfg.backend)
        self._formats = _fourcc_plan(cfg)
        self._fmt_i = 0
        self._force_size = True
        self._exhausted = False

        if _device_disabled(self._src) and not cfg.rtsp:
            print(f"[{name}] device disabled — skip open")
            return

        if not self._open_capture():
            return
        self._opened = True
        self._thread = threading.Thread(target=self._loop, name=f"cam-{name}", daemon=True)
        self._thread.start()

    def _open_capture(self) -> bool:
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        try:
            if self._api is not None and not self.cfg.rtsp:
                self.cap = cv2.VideoCapture(self._src, self._api)
            else:
                self.cap = cv2.VideoCapture(self._src)
        except Exception as exc:
            print(f"[{self.name}] open error {self._src}: {exc}")
            self.cap = None
            return False
        if self.cap is None or not self.cap.isOpened():
            print(f"[{self.name}] cannot open {self._src}")
            self.cap = None
            return False
        fourcc = self._formats[self._fmt_i] if self._formats else ""
        self._tune(fourcc)
        w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 0)
        label = fourcc or "default"
        size = f"{w}x{h}" if self._force_size else "native"
        print(f"[{self.name}] opened {self._src} backend={self.cfg.backend} fourcc={label} {size} {w}x{h} @{fps:.1f}")
        return True

    def _tune(self, fourcc: str) -> None:
        cap = self.cap
        if cap is None:
            return
        # Rut timeout mac dinh ~10s cua V4L2 select() xuong 1s (neu OpenCV ho tro)
        for prop_name, ms in (("CAP_PROP_OPEN_TIMEOUT_MSEC", 2000), ("CAP_PROP_READ_TIMEOUT_MSEC", 1000)):
            prop = getattr(cv2, prop_name, None)
            if prop is not None:
                try:
                    cap.set(prop, ms)
                except Exception:
                    pass
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        if fourcc and len(fourcc) == 4:
            try:
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
            except Exception:
                pass
        if self._force_size:
            if self.cfg.width > 0:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg.width)
            if self.cfg.height > 0:
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.height)
        if self.cfg.fps > 0:
            cap.set(cv2.CAP_PROP_FPS, self.cfg.fps)

    def _try_next_format(self) -> None:
        """Chua co frame: doi fourcc / bo ep resolution. Khong anh huong camera kia."""
        if self._got_frame or self.cfg.rtsp:
            return
        if self._force_size:
            self._force_size = False
            print(f"[{self.name}] no frame — retry native resolution")
            self._open_capture()
            return
        self._force_size = True
        if self._fmt_i + 1 < len(self._formats):
            self._fmt_i += 1
            print(f"[{self.name}] no frame — retry fourcc {self._formats[self._fmt_i] or 'default'}")
            self._open_capture()
            return
        if not self._exhausted:
            self._exhausted = True
            print(
                f"[{self.name}] still no frame on {self._src}. "
                f"Kiem tra node that: v4l2-ctl --list-devices (FCB co the khong phai /dev/video0)"
            )

    def _loop(self) -> None:
        consecutive = 0
        while not self._stop.is_set():
            if self.cap is None or not self.cap.isOpened():
                time.sleep(0.5)
                if not self._got_frame and not self._exhausted:
                    self._try_next_format()
                continue
            try:
                ok, frame = self.cap.read()
            except Exception as exc:
                print(f"[{self.name}] read error: {exc}")
                ok, frame = False, None
            if ok and frame is not None:
                consecutive = 0
                self._got_frame = True
                with self._lock:
                    self._frame = frame
                    self._fail_count = 0
            else:
                consecutive += 1
                with self._lock:
                    self._fail_count = consecutive
                if not self._got_frame and not self._exhausted and consecutive >= 1:
                    consecutive = 0
                    self._try_next_format()
                elif consecutive == 3:
                    print(f"[{self.name}] lost frames — keep other cameras running")
                time.sleep(0.05)

    def read(self) -> np.ndarray | None:
        """Tra frame moi nhat ngay lap tuc (khong block)."""
        with self._lock:
            if self._frame is None:
                return None
            return self._frame.copy()

    def close(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        with self._lock:
            self._frame = None


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
            self._vis_src = OpenCvSource(self._visible_cfg(settings), "visible")
            self._th_src = OpenCvSource(self._thermal_cfg(settings), "thermal")
        elif webcam:
            self._vis_src = OpenCvSource(self._visible_cfg(settings), "visible")

    @staticmethod
    def _visible_cfg(settings: Settings) -> CamDevice:
        base = settings.cameras.visible
        video = getattr(settings.visca, "video", None)
        if video is None or video == "":
            return base
        return base.model_copy(update={"device": video})

    @staticmethod
    def _thermal_cfg(settings: Settings) -> CamDevice:
        base = settings.cameras.thermal
        video = getattr(settings.satis, "video", None)
        if video is None or video == "":
            return base
        return base.model_copy(update={"device": video})

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
        vis_cfg = self._visible_cfg(self.settings)
        th_cfg = self._thermal_cfg(self.settings)
        vw, vh = quality_size(cam.quality, (vis_cfg.width, vis_cfg.height))
        tw, th = th_cfg.width, th_cfg.height
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
                vis = cv2.convertScaleAbs(
                    vis, alpha=max(0.3, cam.contrast / 50.0), beta=int((cam.brightness - 50) * 1.4)
                )
            if therm is not None:
                therm = cv2.resize(therm, (tw, th))
                if th_cfg.colormap:
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
        if webcam is not None:
            self.webcam = webcam
        self.close()
        self.settings = settings
        if not settings.sim:
            self._vis_src = OpenCvSource(self._visible_cfg(settings), "visible")
            self._th_src = OpenCvSource(self._thermal_cfg(settings), "thermal")
        elif self.webcam:
            self._vis_src = OpenCvSource(self._visible_cfg(settings), "visible")
