"""Test từng module phần cứng theo config.yaml.

Chạy trên Jetson (hoặc Windows lab) — nên tạm dừng service trước khi test serial:

  sudo systemctl stop eo-service

  cd ~/eo-control/jetson-service
  source .venv/bin/activate

  python -m eos_service.hw_test ports              # liệt kê /dev/video* + ttyUSB*
  python -m eos_service.hw_test cameras            # đọc 1 frame mỗi camera
  python -m eos_service.hw_test cameras --preview  # mở cửa sổ video (q để thoát)
  python -m eos_service.hw_test cameras --snapshot # lưu JPG vào data/hw_test/
  python -m eos_service.hw_test visca
  python -m eos_service.hw_test satis
  python -m eos_service.hw_test laser
  python -m eos_service.hw_test ptz
  python -m eos_service.hw_test gps
  python -m eos_service.hw_test                    # tất cả
  python -m eos_service.hw_test --config config.yaml cameras visca

  sudo systemctl start eo-service

Không cần GCS. Dùng đúng file config đang chạy service.
SSH không có màn hình: dùng --snapshot rồi scp file về PC xem.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .cameras.hub import OpenCvSource
from .cameras.satis import SatisController
from .cameras.visca import ViscaController
from .config import ROOT, load_settings
from .ptz.controller import PtzController
from .sensors.devices import GpsCompass, LaserRangefinder


MODULES = ("ports", "cameras", "visca", "satis", "laser", "ptz", "gps")


def _ok(msg: str) -> None:
    print(f"  OK  {msg}")


def _fail(msg: str) -> None:
    print(f"  FAIL {msg}")


def _info(msg: str) -> None:
    print(f"  ..  {msg}")


def test_ports(_settings) -> bool:
    print("\n== ports ==")
    try:
        import glob

        videos = sorted(glob.glob("/dev/video*"))
        ttys = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
        if sys.platform.startswith("win"):
            _info("Windows: dùng Device Manager / mode để xem COM")
            try:
                import serial.tools.list_ports

                ports = list(serial.tools.list_ports.comports())
                if not ports:
                    _fail("Không thấy COM nào")
                    return False
                for p in ports:
                    _ok(f"{p.device}  {p.description}")
                return True
            except Exception as exc:
                _fail(str(exc))
                return False
        if videos:
            for v in videos:
                _ok(v)
        else:
            _fail("Không có /dev/video*")
        if ttys:
            for t in ttys:
                _ok(t)
        else:
            _fail("Không có /dev/ttyUSB* / ttyACM*")
        return bool(videos or ttys)
    except Exception as exc:
        _fail(str(exc))
        return False


def test_cameras(settings, *, preview: bool = False, snapshot: bool = False) -> bool:
    print("\n== cameras ==")
    import cv2

    ok = True
    frames: dict[str, object] = {}
    for name, cfg in (("visible", settings.cameras.visible), ("thermal", settings.cameras.thermal)):
        _info(f"{name}: device={cfg.device} backend={cfg.backend} {cfg.width}x{cfg.height}")
        src = OpenCvSource(cfg)
        try:
            frame = None
            for _ in range(12):
                frame = src.read()
                if frame is not None:
                    break
                time.sleep(0.05)
            if frame is None:
                _fail(f"{name}: không đọc được frame")
                ok = False
            else:
                h, w = frame.shape[:2]
                _ok(f"{name}: frame {w}x{h}")
                frames[name] = frame
        finally:
            src.close()

    if snapshot and frames:
        out_dir = Path(settings.record.dir).parent / "hw_test"
        if not out_dir.is_absolute():
            out_dir = ROOT / out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        for name, frame in frames.items():
            path = out_dir / f"{ts}_{name}.jpg"
            cv2.imwrite(str(path), frame)  # type: ignore[arg-type]
            _ok(f"snapshot → {path}")

    if preview and frames:
        _info("Preview: phím q / Esc thoát")
        sources = {}
        try:
            for name, cfg in (("visible", settings.cameras.visible), ("thermal", settings.cameras.thermal)):
                if name not in frames:
                    continue
                sources[name] = OpenCvSource(cfg)
            while True:
                for name, src in sources.items():
                    live = src.read()
                    if live is not None:
                        cv2.imshow(f"EO {name}", live)
                key = cv2.waitKey(30) & 0xFF
                if key in (ord("q"), 27):
                    break
        except Exception as exc:
            _fail(f"preview lỗi (SSH không display?): {exc}")
            _info("Thử: python -m eos_service.hw_test cameras --snapshot")
            ok = False
        finally:
            for src in sources.values():
                src.close()
            cv2.destroyAllWindows()

    return ok


def test_visca(settings) -> bool:
    print("\n== visca (FCB zoom) ==")
    cfg = settings.visca
    _info(f"protocol={cfg.protocol} port={cfg.port} baud={cfg.baud} addr={cfg.address}")
    ctrl = ViscaController(cfg, sim=False)
    try:
        if ctrl.sim:
            _fail("Đang ở sim — không mở được serial VISCA")
            return False
        ctrl.zoom_in(pulse_s=0.25)
        time.sleep(0.4)
        ctrl.zoom_out(pulse_s=0.25)
        time.sleep(0.4)
        ctrl.zoom_stop()
        _ok("Đã gửi ZOOM IN/OUT/STOP")
        return True
    finally:
        ctrl.close()


def test_satis(settings) -> bool:
    print("\n== satis (thermal zoom) ==")
    cfg = settings.satis
    _info(f"protocol={getattr(cfg, 'protocol', 'satis')} port={cfg.port} baud={cfg.baud}")
    ctrl = SatisController(cfg, sim=False)
    try:
        if ctrl.sim:
            _fail("Đang ở sim — không mở được serial SATIS")
            return False
        ctrl.zoom_in(pulse_s=0.25)
        time.sleep(0.4)
        ctrl.zoom_out(pulse_s=0.25)
        time.sleep(0.4)
        ctrl.zoom_stop()
        _ok("Đã gửi ZOOM IN/OUT/STOP")
        return True
    finally:
        ctrl.close()


def test_laser(settings) -> bool:
    print("\n== laser ==")
    cfg = settings.laser
    _info(f"protocol={cfg.protocol} port={cfg.port} baud={cfg.baud}")
    laser = LaserRangefinder(cfg, sim=False)
    try:
        if laser.sim:
            _fail("Đang ở sim — không mở được serial laser")
            return False
        laser.trigger_once()
        deadline = time.perf_counter() + 3.0
        while time.perf_counter() < deadline:
            laser.poll()
            if laser.valid and laser.range_m > 0:
                _ok(f"Khoảng cách {laser.range_m:.2f} m")
                return True
            time.sleep(0.1)
        _fail("Không nhận được đo trong 3s (kiểm tra lệnh / parity / mục tiêu)")
        return False
    finally:
        laser.close()


def test_ptz(settings) -> bool:
    print("\n== ptz ==")
    cfg = settings.ptz
    _info(f"protocol={cfg.protocol} port={cfg.port} baud={cfg.baud} addr={cfg.address}")
    ptz = PtzController(cfg, sim=False)
    try:
        if ptz.sim:
            _fail("Đang ở sim — không mở được serial PTZ")
            return False
        ptz.nudge(0.4, 0.0, speed=0.6)
        for _ in range(8):
            ptz.tick(0.05)
            time.sleep(0.05)
        ptz.stop()
        ptz.nudge(0.0, 0.3, speed=0.6)
        for _ in range(8):
            ptz.tick(0.05)
            time.sleep(0.05)
        ptz.stop()
        _ok(f"Đã nudge pan/tilt — góc nội bộ pan={ptz.pan:.1f} tilt={ptz.tilt:.1f}")
        return True
    finally:
        ptz.close()


def test_gps(settings) -> bool:
    print("\n== gps / compass ==")
    _info(f"gps={settings.gps.port}@{settings.gps.baud} compass={settings.compass.source}")
    nav = GpsCompass(settings, sim=False)
    try:
        if nav.sim:
            _fail("Đang ở sim — không mở được GPS serial")
            return False
        deadline = time.perf_counter() + 5.0
        while time.perf_counter() < deadline:
            nav.poll()
            fix, hdg = nav.snapshot()
            if fix.fix:
                _ok(f"GPS fix lat={fix.lat:.6f} lon={fix.lon:.6f} alt={fix.alt:.1f} hdg={hdg:.1f}")
                return True
            time.sleep(0.2)
        fix, hdg = nav.snapshot()
        _fail(f"Chưa có fix sau 5s (lat={fix.lat:.5f} lon={fix.lon:.5f} hdg={hdg:.1f})")
        return False
    finally:
        nav.close()


HANDLERS = {
    "ports": test_ports,
    "cameras": test_cameras,
    "visca": test_visca,
    "satis": test_satis,
    "laser": test_laser,
    "ptz": test_ptz,
    "gps": test_gps,
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="EO hardware module self-test")
    p.add_argument("--config", default=str(Path(__file__).resolve().parent.parent / "config.yaml"))
    p.add_argument("--preview", action="store_true", help="cameras: mở cửa sổ video (q thoát)")
    p.add_argument("--snapshot", action="store_true", help="cameras: lưu JPG vào data/hw_test/")
    p.add_argument(
        "modules",
        nargs="*",
        default=["all"],
        help=f"all | {' | '.join(MODULES)}",
    )
    args = p.parse_args(argv)

    settings = load_settings(args.config, sim_override=False)
    print(f"Config: {args.config}")
    print(f"sim(file)={settings.sim}  (test ép sim=False cho từng module)")

    wanted = list(args.modules)
    if not wanted or wanted == ["all"] or "all" in wanted:
        wanted = list(MODULES)

    results: dict[str, bool] = {}
    for name in wanted:
        key = name.lower()
        fn = HANDLERS.get(key)
        if not fn:
            print(f"\n== {name} ==\n  FAIL module không hỗ trợ")
            results[key] = False
            continue
        try:
            if key == "cameras":
                results[key] = bool(fn(settings, preview=args.preview, snapshot=args.snapshot))
            else:
                results[key] = bool(fn(settings))
        except Exception as exc:
            _fail(f"exception: {exc}")
            results[key] = False

    print("\n== tổng kết ==")
    failed = [k for k, v in results.items() if not v]
    for k, v in results.items():
        print(f"  {'OK  ' if v else 'FAIL'} {k}")
    if failed:
        print(f"\n{len(failed)} module lỗi: {', '.join(failed)}")
        return 1
    print("\nTất cả module đã chọn PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
