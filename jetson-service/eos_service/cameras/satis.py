from __future__ import annotations

import struct
import threading
import time

from ..config import SatisCfg
from .ports import is_serial_port, is_video_device

# ICD SATIS — TR_IN_OP_FOV
TR_IN_OP_FOV = 0x00DA
ZOOM_IN = 0x0003   # VPC → NFOV
ZOOM_OUT = 0x0004  # VGC → WFOV
ZOOM_STOP = 0x0005


def xor_checksum(data: bytes | bytearray) -> int:
    checksum = 0
    for b in data:
        checksum ^= b
    return checksum & 0xFF


def make_satis_frame(application_frame: bytes) -> bytes:
    """SOH + PROT + N(u16 BE) + application + ETX + XOR checksum."""
    soh, prot, etx = 0x01, 0x02, 0x03  # PROT DATA_A = yêu cầu ACK
    n = len(application_frame)
    frame = bytearray()
    frame.append(soh)
    frame.append(prot)
    frame += struct.pack(">H", n)
    frame += application_frame
    frame.append(etx)
    frame.append(xor_checksum(frame))
    return bytes(frame)


class SatisController:
    """
    Zoom SATIS qua RS422 (pyserial).

    Anh nhiet: OpenCV mo satis.video / cameras.thermal (/dev/video*).
    Neu gan nham /dev/video vao port → tu choi mo serial.
    """

    def __init__(self, cfg: SatisCfg, sim: bool):
        self.cfg = cfg
        self.sim = sim or self._cfg_is_sim(cfg)
        self._ser = None
        self._lock = threading.Lock()
        self._stop_at = 0.0
        self._active = False
        if not self.sim:
            self._open()

    @staticmethod
    def _cfg_is_sim(cfg: SatisCfg) -> bool:
        if (cfg.protocol or "").lower() == "sim":
            return True
        if cfg.enabled is False:
            return True
        return False

    def _open(self) -> None:
        port = self.cfg.port
        if is_video_device(port):
            print(
                f"[satis] port={port} is /dev/video — use OpenCV for video, "
                f"not pyserial. RS422 zoom needs /dev/ttyUSB* or COM*. "
                f"Set cameras.thermal.device or satis.video = {port}"
            )
            self.sim = True
            self._ser = None
            return
        if not is_serial_port(port):
            print(f"[satis] port is not a serial UART ({port}) — skip RS422 zoom")
            self.sim = True
            self._ser = None
            return
        try:
            import serial

            parity = serial.PARITY_NONE
            if self.cfg.parity == "even":
                parity = serial.PARITY_EVEN
            elif self.cfg.parity == "odd":
                parity = serial.PARITY_ODD

            kwargs = {
                "port": str(port),
                "baudrate": self.cfg.baud,
                "bytesize": serial.EIGHTBITS,
                "parity": parity,
                "stopbits": serial.STOPBITS_ONE,
                "timeout": 0.1,
            }
            self._ser = serial.Serial(**kwargs)
            bits = {"none": "8N1", "even": "8E1", "odd": "8O1"}.get(self.cfg.parity, "8E1")
            print(f"[satis] RS422 zoom mo {port} @ {self.cfg.baud} {bits}")
        except Exception as exc:
            print(f"[satis] Khong mo {port}: {exc} — sim zoom")
            self.sim = True
            self._ser = None

    def zoom_in(self, pulse_s: float | None = None) -> None:
        self._send(ZOOM_IN)
        self._arm_auto_stop(pulse_s)

    def zoom_out(self, pulse_s: float | None = None) -> None:
        self._send(ZOOM_OUT)
        self._arm_auto_stop(pulse_s)

    def zoom_stop(self) -> None:
        self._send(ZOOM_STOP)
        with self._lock:
            self._active = False
            self._stop_at = 0.0

    def tick(self) -> None:
        with self._lock:
            due = self._active and self._stop_at > 0 and time.perf_counter() >= self._stop_at
        if due:
            self.zoom_stop()

    def _arm_auto_stop(self, pulse_s: float | None) -> None:
        dur = self.cfg.zoom_pulse_s if pulse_s is None else pulse_s
        with self._lock:
            if dur and dur > 0:
                self._active = True
                self._stop_at = time.perf_counter() + dur
            else:
                self._active = True
                self._stop_at = 0.0

    def _send(self, command: int) -> None:
        application = struct.pack(
            ">HffH",
            TR_IN_OP_FOV,
            float(self.cfg.zoom_speed),
            float(self.cfg.fov_set_point),
            command,
        )
        frame = make_satis_frame(application)
        if self.sim or self._ser is None:
            name = {ZOOM_IN: "IN", ZOOM_OUT: "OUT", ZOOM_STOP: "STOP"}.get(command, hex(command))
            print(f"[satis/sim] ZOOM {name}  {frame.hex(' ').upper()}")
            return
        try:
            with self._lock:
                self._ser.write(frame)
            name = {ZOOM_IN: "IN", ZOOM_OUT: "OUT", ZOOM_STOP: "STOP"}.get(command, hex(command))
            print(f"[satis] TX ZOOM {name}: {frame.hex(' ').upper()}")
        except Exception as exc:
            print(f"[satis] Gui loi: {exc}")

    def close(self) -> None:
        try:
            self.zoom_stop()
        except Exception:
            pass
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    def reconfigure(self, cfg: SatisCfg, sim: bool) -> None:
        self.close()
        self.cfg = cfg
        self.sim = sim or self._cfg_is_sim(cfg)
        self._active = False
        self._stop_at = 0.0
        if not self.sim:
            self._open()
