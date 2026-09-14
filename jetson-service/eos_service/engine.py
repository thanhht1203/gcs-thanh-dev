from __future__ import annotations

import asyncio
import json
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
from .config import Settings
from .geo import compute_fov, target_geolocation
from .media.recorder import Recorder
from .ptz.controller import PtzController
from .sensors.devices import GpsCompass, LaserRangefinder
from .sim.world import SimWorld
from .state import SystemState


JPEG_QUALITY = 75
STREAM_VISIBLE = 0
STREAM_THERMAL = 1


class Engine:
    def __init__(self, settings: Settings, webcam: bool = False):
        self.settings = settings
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
            if self.settings.sim and not self.detector.ok:
                dets = list(self.cameras.sim_dets)
                if self.state.roi:
                    rx, ry, rw, rh = self.state.roi
                    dets = [
                        d
                        for d in dets
                        if d.x + d.w / 2 >= rx
                        and d.x + d.w / 2 <= rx + rw
                        and d.y + d.h / 2 >= ry
                        and d.y + d.h / 2 <= ry + rh
                    ]
            else:
                dets = self.detector.infer(vis, self.state.roi if self.state.roi else None)
                if not dets and self.cameras.sim_dets:
                    dets = list(self.cameras.sim_dets)
        self.state.detections = dets

        if self.state.track_on:
            tracked = keep_track(dets, self.state.track_id)
            if tracked is None and dets:
                tracked = pick_nearest(dets, 0.5, 0.5)
                if tracked:
                    self.state.track_id = tracked.id
            if tracked:
                # auto-center mildly toward target
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

    async def handle_cmd(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        t = msg.get("type")
        st = self.state
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
                # map zoom UI → pulse in/out thô
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
                # bám object gần tâm ROI
                rx, ry, rw, rh = st.roi
                d = pick_nearest(st.detections, rx + rw / 2, ry + rh / 2)
                if d:
                    st.track_id = d.id
                    st.track_on = True
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
