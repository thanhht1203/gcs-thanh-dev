from __future__ import annotations

import threading

from ..config import PtzCfg


class PtzController:
    def __init__(self, cfg: PtzCfg, sim: bool):
        self.cfg = cfg
        self.sim = sim or cfg.protocol == "sim"
        self.pan = 0.0
        self.tilt = 0.0
        self._cmd_pan = 0.0  # -1..1
        self._cmd_tilt = 0.0
        self._goto: tuple[float, float] | None = None
        self._lock = threading.Lock()
        self._ser = None
        if not self.sim:
            self._open_serial()

    def _open_serial(self) -> None:
        try:
            import serial

            self._ser = serial.Serial(self.cfg.port, self.cfg.baud, timeout=0.05)
        except Exception as exc:
            print(f"[ptz] Không mở được {self.cfg.port}: {exc} — chuyển sim")
            self.sim = True

    def nudge(self, pan: float, tilt: float, speed: float = 1.0) -> None:
        with self._lock:
            self._goto = None
            s = max(0.1, min(3.0, speed))
            self._cmd_pan = max(-1.0, min(1.0, pan)) * s
            self._cmd_tilt = max(-1.0, min(1.0, tilt)) * s

    def stop(self) -> None:
        with self._lock:
            self._cmd_pan = 0.0
            self._cmd_tilt = 0.0
            self._goto = None
        self._send_pelco_stop()

    def home(self) -> None:
        self.goto(0.0, 0.0)

    def goto(self, pan: float, tilt: float) -> None:
        pan = max(self.cfg.pan_min, min(self.cfg.pan_max, pan))
        tilt = max(self.cfg.tilt_min, min(self.cfg.tilt_max, tilt))
        with self._lock:
            self._cmd_pan = 0.0
            self._cmd_tilt = 0.0
            self._goto = (pan, tilt)

    def slider(self, pan: float | None, tilt: float | None) -> None:
        with self._lock:
            if pan is not None:
                self.pan = max(self.cfg.pan_min, min(self.cfg.pan_max, pan))
            if tilt is not None:
                self.tilt = max(self.cfg.tilt_min, min(self.cfg.tilt_max, tilt))
            self._goto = None
            self._cmd_pan = 0.0
            self._cmd_tilt = 0.0

    def tick(self, dt: float) -> tuple[float, float]:
        with self._lock:
            if self._goto is not None:
                tp, tt = self._goto
                self.pan = self._approach(self.pan, tp, self.cfg.pan_speed * dt)
                self.tilt = self._approach(self.tilt, tt, self.cfg.tilt_speed * dt)
                if abs(self.pan - tp) < 0.15 and abs(self.tilt - tt) < 0.15:
                    self.pan, self.tilt = tp, tt
                    self._goto = None
            else:
                self.pan += self._cmd_pan * self.cfg.pan_speed * dt
                self.tilt += self._cmd_tilt * self.cfg.tilt_speed * dt
                self.pan = max(self.cfg.pan_min, min(self.cfg.pan_max, self.pan))
                self.tilt = max(self.cfg.tilt_min, min(self.cfg.tilt_max, self.tilt))
            pan, tilt = self.pan, self.tilt
        if not self.sim and (abs(self._cmd_pan) > 0.01 or abs(self._cmd_tilt) > 0.01):
            self._send_pelco_move(self._cmd_pan, self._cmd_tilt)
        return pan, tilt

    @staticmethod
    def _approach(cur: float, target: float, step: float) -> float:
        if cur < target:
            return min(cur + step, target)
        return max(cur - step, target)

    def _send_pelco_stop(self) -> None:
        self._write_pelco(0x00, 0x00, 0, 0)

    def _send_pelco_move(self, pan: float, tilt: float) -> None:
        cmd2 = 0
        if pan > 0.05:
            cmd2 |= 0x02  # right
        elif pan < -0.05:
            cmd2 |= 0x04  # left
        if tilt > 0.05:
            cmd2 |= 0x08  # up
        elif tilt < -0.05:
            cmd2 |= 0x10  # down
        pan_speed = int(min(63, abs(pan) * 63))
        tilt_speed = int(min(63, abs(tilt) * 63))
        self._write_pelco(0x00, cmd2, pan_speed, tilt_speed)

    def _write_pelco(self, cmd1: int, cmd2: int, data1: int, data2: int) -> None:
        if self._ser is None:
            return
        addr = self.cfg.address & 0xFF
        chk = (addr + cmd1 + cmd2 + data1 + data2) & 0xFF
        pkt = bytes([0xFF, addr, cmd1, cmd2, data1, data2, chk])
        try:
            self._ser.write(pkt)
        except Exception:
            pass
