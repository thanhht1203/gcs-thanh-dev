from __future__ import annotations

from datetime import datetime
from pathlib import Path

import cv2
import numpy as np


class Recorder:
    def __init__(self, directory: str, fourcc: str = "mp4v"):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.fourcc = fourcc
        self.writer: cv2.VideoWriter | None = None
        self.path: Path | None = None

    def photo(self, frame: np.ndarray, tag: str = "vis") -> str:
        name = datetime.now().strftime(f"%Y%m%d_%H%M%S_{tag}.jpg")
        path = self.dir / name
        cv2.imwrite(str(path), frame)
        return str(path)

    def start(self, frame: np.ndarray, fps: int = 60) -> str:
        self.stop()
        h, w = frame.shape[:2]
        name = datetime.now().strftime("rec_%Y%m%d_%H%M%S.mp4")
        self.path = self.dir / name
        fourcc = cv2.VideoWriter_fourcc(*self.fourcc[:4].ljust(4, " "))
        self.writer = cv2.VideoWriter(str(self.path), fourcc, fps, (w, h))
        return str(self.path)

    def write(self, frame: np.ndarray) -> None:
        if self.writer is None:
            return
        self.writer.write(frame)

    def stop(self) -> str | None:
        if self.writer is not None:
            self.writer.release()
            self.writer = None
        p = str(self.path) if self.path else None
        self.path = None
        return p

    def list_files(self) -> list[dict]:
        items = []
        for p in sorted(self.dir.glob("*"), reverse=True):
            if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".mp4", ".avi"}:
                items.append({"name": p.name, "size": p.stat().st_size, "mtime": p.stat().st_mtime})
        return items[:200]

    def reconfigure(self, directory: str, fourcc: str) -> None:
        was_recording = self.writer is not None
        self.stop()
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.fourcc = fourcc
        if was_recording:
            print("[record] Đã dừng ghi hình do đổi thư mục/config")
