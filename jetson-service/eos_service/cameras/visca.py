from __future__ import annotations

import threading
import time

from ..config import ViscaCfg

# VISCA FCB-EV9520L — zoom tele/wide/stop
ZOOM_STOP = bytes([0x81, 0x01, 0x04, 0x07, 0x00, 0xFF])
ZOOM_IN = bytes([0x81, 0x01, 0x04, 0x07, 0x02, 0xFF])
ZOOM_OUT = bytes([0x81, 0x01, 0x04, 0x07, 0x03, 0xFF])


class ViscaController:
    """Điều khiển zoom camera ảnh thường Sony FCB-EV9520L qua VISCA."""

    def __init__(self, cfg: ViscaCfg, sim: bool):
        self.cfg = cfg
        self.sim = sim or not cfg.enabled
        self._ser = None
        self._lock = threading.Lock()
        self._stop_at = 0.0
        self._active = False
        if not self.sim:
            self._open()

    def _open(self) -> None:
        try:
            import serial

            parity = serial.PARITY_NONE
            if self.cfg.parity == "even":
                parity = serial.PARITY_EVEN
            elif self.cfg.parity == "odd":
                parity = serial.PARITY_ODD

            self._ser = serial.Serial(
                port=self.cfg.port,
                baudrate=self.cfg.baud,
                bytesize=serial.EIGHTBITS,
                parity=parity,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
            )
            print(f"[visca] FCB mở {self.cfg.port} @ {self.cfg.baud} 8N1")
        except Exception as exc:
            print(f"[visca] Không mở {self.cfg.port}: {exc} — sim zoom")
            self.sim = True
            self._ser = None

    def zoom_in(self, pulse_s: float | None = None) -> None:
        self._send(ZOOM_IN, "ZOOM IN")
        self._arm_auto_stop(pulse_s)

    def zoom_out(self, pulse_s: float | None = None) -> None:
        self._send(ZOOM_OUT, "ZOOM OUT")
        self._arm_auto_stop(pulse_s)

    def zoom_stop(self) -> None:
        self._send(ZOOM_STOP, "ZOOM STOP")
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
                    print(f"[visca] {name}: {command.hex(' ').upper()}")
        except Exception as exc:
            print(f"[visca] Gửi lỗi: {exc}")

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
        self.sim = sim or not cfg.enabled
        self._active = False
        self._stop_at = 0.0
        if not self.sim:
            self._open()
