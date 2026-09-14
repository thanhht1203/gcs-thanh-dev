from __future__ import annotations

import math
import threading
import time

from ..config import Settings
from ..state import GpsFix


def _parity_const(name: str):
    import serial

    return {
        "none": serial.PARITY_NONE,
        "even": serial.PARITY_EVEN,
        "odd": serial.PARITY_ODD,
    }.get((name or "none").lower(), serial.PARITY_NONE)


def _try_serial(
    port: str,
    baud: int,
    *,
    parity: str = "none",
    timeout: float = 0.1,
):
    try:
        import serial

        return serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=_parity_const(parity),
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
        )
    except Exception as exc:
        print(f"[sensor] Không mở {port}: {exc}")
        return None


class LaserRangefinder:
    """
    Hỗ trợ:
      - lrf7047 : LRF 7047 (ASCII >LM,Md,3*CS\\r, 57600 8E1)
      - generic / lightware / sim
    """

    def __init__(self, cfg, sim: bool):
        self.cfg = cfg
        self.sim = sim or cfg.protocol == "sim"
        self.range_m = 0.0
        self.valid = False
        self._ser = None
        self._buf = ""
        self._last_trigger = 0.0
        self._lock = threading.Lock()
        if not self.sim:
            parity = getattr(cfg, "parity", "even" if cfg.protocol == "lrf7047" else "none")
            self._ser = _try_serial(cfg.port, cfg.baud, parity=parity)
            if self._ser is None:
                self.sim = True
            else:
                print(f"[laser] {cfg.protocol} mở {cfg.port} @ {cfg.baud}")
                try:
                    self._ser.reset_input_buffer()
                except Exception:
                    pass

    # ----- LRF 7047 helpers -----
    @staticmethod
    def _lrf_checksum(body: str) -> str:
        return f"{sum(ord(c) for c in body) & 0xFF:02X}"

    @classmethod
    def _lrf_command(cls, body: str) -> str:
        # Frame: >LM,Md,3*D5\r  — checksum trên body (không gồm '>')
        return f">{body}*{cls._lrf_checksum(body)}\r"

    def measure_sim(self, tilt: float, height_m: float, zoom: float) -> None:
        if tilt >= -0.4:
            self.range_m = max(30.0, 180.0 + 40.0 * math.sin(time.time() / 3.0))
            self.valid = True
            return
        elev = math.radians(tilt)
        r = height_m / max(math.sin(-elev), 0.05)
        r = min(r, 2500.0)
        self.range_m = r + 1.5 * math.sin(time.time() * 2)
        self.valid = True

    def poll(self) -> None:
        if self.sim or self._ser is None:
            return
        if self.cfg.protocol == "lrf7047":
            self._poll_lrf7047()
        else:
            self._poll_generic()

    def maybe_continuous(self, enabled: bool) -> None:
        """Gửi đo định kỳ khi continuous (LRF 7047)."""
        if not enabled or self.sim:
            return
        if self.cfg.protocol != "lrf7047":
            return
        interval = float(getattr(self.cfg, "measure_interval_s", 0.8) or 0.8)
        now = time.perf_counter()
        if now - self._last_trigger >= interval:
            self.trigger_once()

    def trigger_once(self) -> None:
        self._last_trigger = time.perf_counter()
        if self.sim or self._ser is None:
            return
        if self.cfg.protocol == "lrf7047":
            cmd = self._lrf_command(getattr(self.cfg, "measure_cmd", "LM,Md,3") or "LM,Md,3")
            try:
                self._ser.reset_input_buffer()
                self._ser.write(cmd.encode("ascii"))
                self._ser.flush()
                print(f"[laser] TX: {cmd.replace(chr(13), '\\r')}")
            except Exception as exc:
                print(f"[laser] Gửi lỗi: {exc}")
            return
        try:
            self._ser.write(b"\n")
        except Exception:
            pass

    def _poll_lrf7047(self) -> None:
        assert self._ser is not None
        try:
            n = self._ser.in_waiting
            if n:
                chunk = self._ser.read(n).decode("ascii", errors="ignore")
                self._buf += chunk
            # Kết thúc khi gặp < (OK) hoặc ! (fail), hoặc đã có frame đo
            done = "<" in self._buf or "!" in self._buf or ("* " in self._buf)
            if ">" in self._buf and "*" in self._buf and ("\r" in self._buf or "\n" in self._buf or "<" in self._buf):
                done = True
            if not done and len(self._buf) < 8:
                return
            if not done and time.perf_counter() - self._last_trigger < 0.05:
                return
            if self._buf:
                data = self._buf
                self._buf = ""
                print(f"[laser] RX: {data.replace(chr(13), '\\r')}")
                self._parse_lrf7047(data)
        except Exception:
            pass

    def _parse_lrf7047(self, response: str) -> None:
        """
        Frame: >LM,Md,range1,range2,range3*CS
        range: v##### (cm hợp lệ), T##### (cảnh báo nhiệt), R... (lỗi)
        """
        for line in response.replace("\r", "\n").split("\n"):
            if ">LM,Md," not in line:
                continue
            try:
                body = line.split("*")[0]
                parts = body.split(",")
                ranges = parts[2:]
                best_m = None
                best_valid = False
                for r in ranges:
                    if not r:
                        continue
                    status, value = r[0], r[1:]
                    if status in ("v", "T") and value.isdigit():
                        dist_m = int(value) / 100.0
                        if best_m is None or dist_m < best_m:
                            best_m = dist_m
                            best_valid = True
                    elif status == "R":
                        continue
                if best_valid and best_m is not None:
                    with self._lock:
                        self.range_m = best_m
                        self.valid = True
                    return
            except Exception as exc:
                print(f"[laser] Parse lỗi: {exc}")
        # Có dấu ! = lệnh thất bại
        if "!" in response:
            with self._lock:
                self.valid = False

    def _poll_generic(self) -> None:
        assert self._ser is not None
        try:
            n = self._ser.in_waiting
            if n:
                self._buf += self._ser.read(n).decode("utf-8", errors="ignore")
            if "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                self._parse_generic(line.strip())
        except Exception:
            pass

    def _parse_generic(self, line: str) -> None:
        try:
            if "D:" in line.upper():
                num = "".join(ch for ch in line.split(":", 1)[1] if ch.isdigit() or ch == ".")
                self.range_m = float(num)
                self.valid = self.range_m > 0
                return
            parts = line.replace(",", " ").split()
            for p in reversed(parts):
                try:
                    val = float(p)
                    if 0.5 < val < 20000:
                        self.range_m = val
                        self.valid = True
                        return
                except ValueError:
                    continue
        except Exception:
            pass


class GpsCompass:
    def __init__(self, settings: Settings, sim: bool):
        self.settings = settings
        self.sim = sim
        self.fix = GpsFix(
            lat=settings.platform.default_lat,
            lon=settings.platform.default_lon,
            alt=settings.platform.default_alt,
            fix=True if sim else False,
        )
        self.heading = settings.platform.default_heading
        self._gps_ser = None if sim else _try_serial(settings.gps.port, settings.gps.baud)
        self._cmp_ser = None
        if not sim and settings.compass.source == "serial":
            self._cmp_ser = _try_serial(settings.compass.port, settings.compass.baud)
        self._buf = b""
        self._lock = threading.Lock()

    def poll(self) -> None:
        if self.sim:
            t = time.time()
            with self._lock:
                self.fix.lat = self.settings.platform.default_lat + 0.00002 * math.sin(t / 18)
                self.fix.lon = self.settings.platform.default_lon + 0.00002 * math.cos(t / 22)
                self.fix.fix = True
            return
        for ser in (self._gps_ser, self._cmp_ser):
            if ser is None:
                continue
            try:
                n = ser.in_waiting
                if n:
                    self._buf += ser.read(n)
                while b"\n" in self._buf:
                    line, self._buf = self._buf.split(b"\n", 1)
                    self._nmea(line.decode("ascii", errors="ignore").strip())
            except Exception:
                pass

    def _nmea(self, line: str) -> None:
        if not line.startswith("$"):
            return
        parts = line.split(",")
        talker = parts[0][3:] if len(parts[0]) >= 6 else parts[0]
        if talker in ("GGA",) and len(parts) > 9:
            lat = _nmea_latlon(parts[2], parts[3])
            lon = _nmea_latlon(parts[4], parts[5])
            try:
                alt = float(parts[9] or 0)
                qual = int(parts[6] or 0)
            except ValueError:
                alt, qual = 0.0, 0
            if lat is not None and lon is not None:
                with self._lock:
                    self.fix = GpsFix(lat=lat, lon=lon, alt=alt, fix=qual > 0)
        elif talker in ("RMC",) and len(parts) > 8:
            lat = _nmea_latlon(parts[3], parts[4])
            lon = _nmea_latlon(parts[5], parts[6])
            try:
                cog = float(parts[8]) if parts[8] else None
            except ValueError:
                cog = None
            if lat is not None and lon is not None:
                with self._lock:
                    self.fix.lat, self.fix.lon, self.fix.fix = lat, lon, parts[2] == "A"
                    if cog is not None:
                        self.heading = cog
        elif talker in ("HDT", "HDM") and len(parts) > 1:
            try:
                with self._lock:
                    self.heading = float(parts[1])
            except ValueError:
                pass

    def snapshot(self) -> tuple[GpsFix, float]:
        with self._lock:
            return GpsFix(self.fix.lat, self.fix.lon, self.fix.alt, self.fix.fix), self.heading


def _nmea_latlon(raw: str, hemi: str) -> float | None:
    if not raw or not hemi:
        return None
    try:
        if "." not in raw:
            return None
        deg_len = 2 if hemi in "NS" else 3
        deg = float(raw[:deg_len])
        minutes = float(raw[deg_len:])
        val = deg + minutes / 60.0
        if hemi in "SW":
            val = -val
        return val
    except ValueError:
        return None
