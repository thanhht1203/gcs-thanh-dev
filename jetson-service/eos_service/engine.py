from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from .ai.detector import Detector, keep_track, pick_nearest
from .cameras.hub import CameraHub
from .cameras.satis import SatisController
from .config import Settings, merge_settings, save_settings, settings_to_dict
from .geo import compute_fov, target_geolocation
from .media.recorder import Recorder
from .ptz.controller import PtzController
from .sensors.devices import GpsCompass, LaserRangefinder
from .sim.world import SimWorld
from .state import Detection, SystemState


JPEG_QUALITY = 75
STREAM_VISIBLE = 0
STREAM_THERMAL = 1


def _center_in_roi(d: Detection, roi: tuple[float, float, float, float]) -> bool:
    rx, ry, rw, rh = roi
    cx = d.x + d.w / 2
    cy = d.y + d.h / 2
    return rx <= cx <= rx + rw and ry <= cy <= ry + rh


def _follow_roi(d: Detection, pad: float = 0.35) -> tuple[float, float, float, float]:
    """Mở rộng bbox mục tiêu thành ROI theo dõi (chuẩn hóa 0–1)."""
    pw = d.w * (1.0 + pad)
    ph = d.h * (1.0 + pad)
    pw = max(pw, 0.06)
    ph = max(ph, 0.08)
    cx = d.x + d.w / 2
    cy = d.y + d.h / 2
    x = max(0.0, min(1.0 - pw, cx - pw / 2))
    y = max(0.0, min(1.0 - ph, cy - ph / 2))
    if x + pw > 1.0:
        pw = 1.0 - x
    if y + ph > 1.0:
        ph = 1.0 - y
    return (x, y, pw, ph)


class Engine:
    def __init__(self, settings: Settings, webcam: bool = False, config_path: str | Path | None = None):
        self.settings = settings
        self.config_path = Path(config_path) if config_path else Path("config.yaml")
        self.webcam = webcam
        self.state = SystemState(sim=settings.sim)
        self.state.camera.quality = "720p" if settings.sim else "1080p"
        self.state.camera.fps = settings.cameras.visible.fps
        self.world = SimWorld(height_m=settings.platform.height_m) if settings.sim else None
        self.cameras = CameraHub(settings, self.world, webcam=webcam)
        self.ptz = PtzController(settings.ptz, settings.sim)
        self.laser = LaserRangefinder(settings.laser, settings.sim)
        self.satis = SatisController(settings.satis, settings.sim)
        self.nav = GpsCompass(settings, settings.sim)
        self.detector = Detector(settings.ai, settings.sim)
        self.recorder = Recorder(settings.record.dir, settings.record.fourcc)
        self.clients: set[WebSocket] = set()
        self._stop = asyncio.Event()
        self._last_tick = time.perf_counter()
        self._apply_lock = threading.Lock()

    async def loop(self) -> None:
        while not self._stop.is_set():
            t0 = time.perf_counter()
            dt = t0 - self._last_tick
            self._last_tick = t0
            await asyncio.to_thread(self._step, dt)
            vis = self.cameras.get_visible()
            th = self.cameras.get_thermal()
            if self.state.recording:
                self.recorder.write(vis)
            if not self.clients:
                fps = max(5, int(self.state.camera.fps))
                elapsed = time.perf_counter() - t0
                await asyncio.sleep(max(0.0, 1.0 / fps - elapsed))
                continue
            vjpg = encode_jpeg(vis)
            tjpg = encode_jpeg(th, quality=70)
            telemetry = json.dumps(self.state.telemetry(), ensure_ascii=False)
            dead: list[WebSocket] = []
            for ws in list(self.clients):
                try:
                    await ws.send_text(telemetry)
                    await ws.send_bytes(bytes([STREAM_VISIBLE]) + vjpg)
                    await ws.send_bytes(bytes([STREAM_THERMAL]) + tjpg)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.clients.discard(ws)
            fps = max(5, int(self.state.camera.fps))
            elapsed = time.perf_counter() - t0
            await asyncio.sleep(max(0.0, 1.0 / fps - elapsed))

    def _step(self, dt: float) -> None:
        with self._apply_lock:
            self._step_locked(dt)

    def _step_locked(self, dt: float) -> None:
        pan, tilt = self.ptz.tick(dt)
        self.state.pan, self.state.tilt = pan, tilt

        vis_cfg = self.settings.cameras.visible
        aspect = vis_cfg.width / max(vis_cfg.height, 1)
        self.state.fov_h, self.state.fov_v = compute_fov(self.settings.optics.fov_h_1x, self.state.zoom, aspect)

        self.nav.poll()
        gps, heading = self.nav.snapshot()
        self.state.gps = gps
        self.state.heading = heading

        self.cameras.capture(pan, tilt, heading, self.state.fov_h, self.state.camera)
        vis = self.cameras.get_visible()

        if self.settings.sim:
            self.laser.measure_sim(tilt, self.settings.platform.height_m, self.state.zoom)
        else:
            self.laser.maybe_continuous(self.state.laser_continuous)
            self.laser.poll()
        self.state.laser_m = self.laser.range_m
        self.state.laser_valid = self.laser.valid
        self.satis.tick()

        dets = []
        if self.state.detect_on:
            # Khi đang bám: detect cả khung hình để ID không mất khi mục tiêu ra khỏi ROI cũ.
            # ROI chỉ dùng làm cửa sổ tìm khi chưa khóa track.
            use_roi = self.state.roi if (self.state.roi and not self.state.track_on) else None
            if self.settings.sim and not self.detector.ok:
                dets = list(self.cameras.sim_dets)
                if use_roi:
                    dets = [d for d in dets if _center_in_roi(d, use_roi)]
            else:
                dets = self.detector.infer(vis, use_roi)
                if not dets and self.cameras.sim_dets:
                    dets = list(self.cameras.sim_dets)
                    if use_roi:
                        dets = [d for d in dets if _center_in_roi(d, use_roi)]
        self.state.detections = dets

        if self.state.track_on:
            tracked = keep_track(dets, self.state.track_id)
            if tracked is None and self.state.roi:
                # mất ID tạm thời → chọn lại trong vùng ROI đang theo
                rx, ry, rw, rh = self.state.roi
                tracked = pick_nearest(dets, rx + rw / 2, ry + rh / 2)
                if tracked and _center_in_roi(tracked, self.state.roi):
                    self.state.track_id = tracked.id
                else:
                    tracked = None
            if tracked is None and dets:
                tracked = pick_nearest(dets, 0.5, 0.5)
                if tracked:
                    self.state.track_id = tracked.id
            if tracked:
                # ROI / bbox vùng bám đi theo mục tiêu
                self.state.roi = _follow_roi(tracked, pad=0.35)
                cx = tracked.x + tracked.w / 2
                cy = tracked.y + tracked.h / 2
                err_x = cx - 0.5
                err_y = cy - 0.5
                if abs(err_x) > 0.04 or abs(err_y) > 0.04:
                    self.ptz.nudge(err_x * 1.8, -err_y * 1.8, speed=0.7)
            else:
                self.ptz.stop()

        rng = self.state.laser_m if self.state.laser_valid else None
        self.state.target_geo = target_geolocation(
            gps,
            heading,
            pan,
            tilt,
            rng,
            self.settings.platform.height_m,
        )

    def get_config_payload(self) -> dict[str, Any]:
        return {
            "type": "config",
            "ok": True,
            "path": str(self.config_path),
            "config": settings_to_dict(self.settings),
            "notes": {
                "host_port": "host/port chỉ có hiệu lực sau khi khởi động lại service",
            },
        }

    def apply_config(self, patch: dict[str, Any], *, persist: bool = True) -> dict[str, Any]:
        """Ghi config (tuỳ chọn) và hot-apply thiết bị — không restart process."""
        errors: list[str] = []
        warnings: list[str] = []
        try:
            new_settings = merge_settings(self.settings, patch)
        except Exception as exc:
            return {
                "type": "config",
                "ok": False,
                "error": f"Config không hợp lệ: {exc}",
                "config": settings_to_dict(self.settings),
            }

        listen_host, listen_port = self.settings.host, self.settings.port
        saved_host, saved_port = new_settings.host, new_settings.port
        if saved_host != listen_host or saved_port != listen_port:
            warnings.append("host/port đã lưu; cần restart service để đổi cổng lắng nghe")

        with self._apply_lock:
            try:
                if persist:
                    save_settings(new_settings, self.config_path)

                sim_changed = new_settings.sim != self.settings.sim
                self.settings = new_settings
                self.state.sim = new_settings.sim

                if new_settings.sim and self.world is None:
                    self.world = SimWorld(height_m=new_settings.platform.height_m)
                elif not new_settings.sim:
                    self.world = None
                elif self.world is not None:
                    self.world.height_m = new_settings.platform.height_m

                self.cameras.world = self.world
                self.cameras.reconfigure(new_settings, webcam=self.webcam)
                self.ptz.reconfigure(new_settings.ptz, new_settings.sim)
                self.laser.reconfigure(new_settings.laser, new_settings.sim)
                self.satis.reconfigure(new_settings.satis, new_settings.sim)
                self.nav.reconfigure(new_settings, new_settings.sim)
                self.detector.reconfigure(new_settings.ai, new_settings.sim)
                self.recorder.reconfigure(new_settings.record.dir, new_settings.record.fourcc)
                if self.state.recording:
                    self.state.recording = False

                # giữ host/port runtime (uvicorn đã bind)
                self.settings.host = listen_host
                self.settings.port = listen_port

                if sim_changed:
                    warnings.append("Đã đổi chế độ sim — thiết bị đã mở lại theo cấu hình mới")
            except Exception as exc:
                errors.append(str(exc))

        ok = len(errors) == 0
        cfg_out = settings_to_dict(self.settings)
        if persist and ok:
            cfg_out["host"] = saved_host
            cfg_out["port"] = saved_port
        return {
            "type": "config",
            "ok": ok,
            "applied": ok,
            "saved": persist and ok,
            "path": str(self.config_path),
            "config": cfg_out,
            "errors": errors,
            "warnings": warnings,
        }

    async def handle_cmd(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        t = msg.get("type")
        st = self.state
        if t == "config":
            action = msg.get("action", "get")
            request_id = msg.get("requestId")
            if action == "get":
                payload = self.get_config_payload()
                if request_id is not None:
                    payload["requestId"] = request_id
                return payload
            if action in ("set", "apply"):
                patch = msg.get("config")
                if not isinstance(patch, dict):
                    err = {"type": "config", "ok": False, "error": "Thiếu object config"}
                    if request_id is not None:
                        err["requestId"] = request_id
                    return err
                persist = bool(msg.get("persist", True))
                payload = await asyncio.to_thread(self.apply_config, patch, persist=persist)
                if request_id is not None:
                    payload["requestId"] = request_id
                return payload
            err = {"type": "config", "ok": False, "error": f"action không hỗ trợ: {action}"}
            if request_id is not None:
                err["requestId"] = request_id
            return err
        if t == "ptz":
            action = msg.get("action")
            if action == "nudge":
                self.ptz.nudge(float(msg.get("pan", 0)), float(msg.get("tilt", 0)), float(msg.get("speed", 1)))
            elif action == "stop":
                self.ptz.stop()
            elif action == "home":
                st.track_on = False
                self.ptz.home()
            elif action == "goto":
                st.track_on = False
                self.ptz.goto(float(msg.get("pan", 0)), float(msg.get("tilt", 0)))
            elif action == "slider":
                st.track_on = False
                self.ptz.slider(msg.get("pan"), msg.get("tilt"))
        elif t == "zoom":
            action = msg.get("action")
            zmin, zmax = self.settings.optics.zoom_min, self.settings.optics.zoom_max
            if action == "in":
                st.zoom = min(zmax, st.zoom * 1.15)
                self.satis.zoom_in()
            elif action == "out":
                st.zoom = max(zmin, st.zoom / 1.15)
                self.satis.zoom_out()
            elif action == "stop":
                self.satis.zoom_stop()
            elif action == "set":
                st.zoom = max(zmin, min(zmax, float(msg.get("value", 1))))
                mid = (zmin + zmax) / 2
                if st.zoom >= mid:
                    self.satis.zoom_in(pulse_s=0.2)
                else:
                    self.satis.zoom_out(pulse_s=0.2)
        elif t == "camera":
            if "autofocus" in msg:
                st.camera.autofocus = bool(msg["autofocus"])
            if "brightness" in msg:
                st.camera.brightness = int(msg["brightness"])
            if "contrast" in msg:
                st.camera.contrast = int(msg["contrast"])
            if "quality" in msg:
                st.camera.quality = str(msg["quality"])
            if "fps" in msg:
                st.camera.fps = int(msg["fps"])
        elif t == "view":
            main = msg.get("main", "visible")
            if main in ("visible", "thermal"):
                st.camera.source = main
        elif t == "laser":
            action = msg.get("action")
            if action == "once":
                self.laser.trigger_once()
                st.laser_continuous = True
            elif action == "continuous":
                st.laser_continuous = bool(msg.get("enabled", True))
        elif t == "detect":
            st.detect_on = bool(msg.get("enabled", True))
            if not st.detect_on:
                st.track_on = False
                st.track_id = None
        elif t == "track":
            action = msg.get("action")
            if action == "stop":
                st.track_on = False
                st.track_id = None
                st.roi = None
                self.ptz.stop()
            elif action == "click":
                x, y = float(msg.get("x", 0.5)), float(msg.get("y", 0.5))
                d = pick_nearest(st.detections, x, y)
                if d:
                    st.track_id = d.id
                    st.track_on = True
                    st.roi = None
            elif action == "nearest":
                d = pick_nearest(st.detections, 0.5, 0.5)
                if d:
                    st.track_id = d.id
                    st.track_on = True
            elif action == "roi":
                st.roi = (
                    float(msg.get("x", 0)),
                    float(msg.get("y", 0)),
                    float(msg.get("w", 0.2)),
                    float(msg.get("h", 0.2)),
                )
                st.detect_on = True
                # Ưu tiên detection hiện có trong ROI; nếu chưa có thì chờ frame sau
                pool = st.detections or list(self.cameras.sim_dets)
                in_roi = [d for d in pool if _center_in_roi(d, st.roi)]
                rx, ry, rw, rh = st.roi
                d = pick_nearest(in_roi or pool, rx + rw / 2, ry + rh / 2)
                if d:
                    st.track_id = d.id
                    st.track_on = True
                    st.roi = _follow_roi(d, pad=0.35)
        elif t == "record":
            action = msg.get("action")
            vis = self.cameras.get_visible()
            if action == "photo":
                path = self.recorder.photo(vis, "vis")
                self.recorder.photo(self.cameras.get_thermal(), "ir")
                st.last_photo = path
                return {"type": "photo", "path": path}
            elif action == "start":
                self.recorder.start(vis, st.camera.fps)
                st.recording = True
            elif action == "stop":
                self.recorder.stop()
                st.recording = False
        return None

    def stop(self) -> None:
        self._stop.set()
        self.satis.close()
        self.cameras.close()
        self.ptz.close()
        self.laser.close()
        self.nav.close()
        self.recorder.stop()


def encode_jpeg(frame: np.ndarray, quality: int = JPEG_QUALITY) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return buf.tobytes() if ok else b""


def create_app(engine: Engine) -> FastAPI:
    app = FastAPI(title="EO Control Jetson Service", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"ok": True, "sim": engine.settings.sim, "clients": len(engine.clients)}

    @app.get("/config")
    def get_config():
        return engine.get_config_payload()

    @app.put("/config")
    def put_config(body: dict[str, Any]):
        patch = body.get("config", body)
        if not isinstance(patch, dict):
            return JSONResponse({"type": "config", "ok": False, "error": "body không hợp lệ"}, status_code=400)
        return engine.apply_config(patch, persist=bool(body.get("persist", True)))

    @app.get("/snapshot/visible")
    def snap_vis():
        return Response(encode_jpeg(engine.cameras.get_visible()), media_type="image/jpeg")

    @app.get("/snapshot/thermal")
    def snap_th():
        return Response(encode_jpeg(engine.cameras.get_thermal()), media_type="image/jpeg")

    @app.get("/recordings")
    def recordings():
        return engine.recorder.list_files()

    @app.get("/recordings/{name}")
    def recording_file(name: str):
        path = Path(engine.recorder.dir) / name
        if not path.exists() or path.parent.resolve() != Path(engine.recorder.dir).resolve():
            return JSONResponse({"error": "not found"}, status_code=404)
        return FileResponse(path)

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        engine.clients.add(ws)
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                extra = await engine.handle_cmd(msg)
                if extra:
                    await ws.send_text(json.dumps(extra, ensure_ascii=False))
        except WebSocketDisconnect:
            pass
        finally:
            engine.clients.discard(ws)

    @app.on_event("startup")
    async def startup():
        asyncio.create_task(engine.loop())

    @app.on_event("shutdown")
    async def shutdown():
        engine.stop()

    return app
