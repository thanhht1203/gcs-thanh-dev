from __future__ import annotations

import threading
import time

from ..config import ViscaCfg
from .ports import is_serial_port, is_video_device


class ViscaController:
    """
    Zoom FCB-EV9520L qua VISCA (pyserial).

    Anh thuong: OpenCV mo visca.video / cameras.visible (/dev/video*).
    Neu gan nham /dev/video vao port → tu choi mo serial.
    """

    def __init__(self, cfg: ViscaCfg, sim: bool):
        self.cfg = cfg
        self.sim = sim or self._cfg_is_sim(cfg)
        self._ser = None
        self._lock = threading.Lock()
        self._stop_at = 0.0
        self._active = False
        if not self.sim:
            self._open()

    @staticmethod
    def _cfg_is_sim(cfg: ViscaCfg) -> bool:
        if (cfg.protocol or "").lower() == "sim":
            return True
        if hasattr(cfg, "enabled") and cfg.enabled is False:
            return True
        return False

    def _addr_byte(self) -> int:
        return 0x80 | max(1, min(7, int(self.cfg.address)))

    def _cmd(self, zoom_op: int) -> bytes:
        return bytes([self._addr_byte(), 0x01, 0x04, 0x07, zoom_op & 0xFF, 0xFF])

    def _open(self) -> None:
        port = self.cfg.port
        if is_video_device(port):
            print(
                f"[visca] port={port} is /dev/video — use OpenCV for video, "
                f"not pyserial. VISCA zoom needs /dev/ttyUSB* or COM*. "
                f"Set cameras.visible.device or visca.video = {port}"
            )
            self.sim = True
            self._ser = None
            return
        if not is_serial_port(port):
            print(f"[visca] port is not a serial UART ({port}) — skip VISCA zoom")
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

            self._ser = serial.Serial(
                port=str(port),
                baudrate=self.cfg.baud,
                bytesize=serial.EIGHTBITS,
                parity=parity,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
            )
            bits = {"none": "8N1", "even": "8E1", "odd": "8O1"}.get(self.cfg.parity, "8N1")
            print(f"[visca] VISCA zoom mo {port} @ {self.cfg.baud} {bits} addr={self.cfg.address}")
        except Exception as exc:
            print(f"[visca] Khong mo {port}: {exc} — sim zoom")
            self.sim = True
            self._ser = None

    def zoom_in(self, pulse_s: float | None = None) -> None:
        self._send(self._cmd(0x02), "ZOOM IN")
        self._arm_auto_stop(pulse_s)

    def zoom_out(self, pulse_s: float | None = None) -> None:
        self._send(self._cmd(0x03), "ZOOM OUT")
        self._arm_auto_stop(pulse_s)

    def zoom_stop(self) -> None:
        self._send(self._cmd(0x00), "ZOOM STOP")
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

    def _send(self, command: bytes, name: str) -> None:
        if self.sim or self._ser is None:
            print(f"[visca/sim] {name}: {command.hex(' ').upper()}")
            return
        try:
            with self._lock:
                self._ser.write(command)
            time.sleep(0.05)
            with self._lock:
                if self._ser is not None and self._ser.in_waiting:
                    response = self._ser.read(self._ser.in_waiting)
                    print(f"[visca] {name} TX {command.hex(' ').upper()}  RX {response.hex(' ').upper()}")
                else:
                    print(f"[visca] TX {name}: {command.hex(' ').upper()}")
        except Exception as exc:
            print(f"[visca] Gui loi: {exc}")

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

    def reconfigure(self, cfg: ViscaCfg, sim: bool) -> None:
        self.close()
        self.cfg = cfg
        self.sim = sim or self._cfg_is_sim(cfg)
        self._active = False
        self._stop_at = 0.0
        if not self.sim:
            self._open()
