from __future__ import annotations

import re

_VIDEO_RE = re.compile(r"^/dev/video\d+$", re.I)


def is_video_device(port: str | int | None) -> bool:
    """True nếu path là V4L2 video — phải mở bằng OpenCV, không phải pyserial."""
    if port is None:
        return False
    s = str(port).strip()
    return bool(_VIDEO_RE.match(s))


def is_serial_port(port: str | int | None) -> bool:
    """Chỉ tty/COM mới được mở bằng pyserial."""
    if port is None:
        return False
    s = str(port).strip()
    if not s or is_video_device(s):
        return False
    low = s.lower()
    if low.startswith("com") and low[3:].isdigit():
        return True
    if low.startswith("/dev/tty"):
        return True
    if low.startswith("/dev/serial"):
        return True
    return False
