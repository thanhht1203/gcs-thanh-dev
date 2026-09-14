from __future__ import annotations

from typing import Sequence

import numpy as np

from ..config import AiCfg
from ..state import Detection

CLASS_NAMES = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


class Detector:
    def __init__(self, cfg: AiCfg, sim: bool):
        self.cfg = cfg
        self.sim = sim
        self.model = None
        self.ok = False
        if sim:
            return
        if not cfg.use_ultralytics:
            return
        try:
            from ultralytics import YOLO

            self.model = YOLO(cfg.model)
            self.ok = True
            print(f"[ai] Loaded {cfg.model}")
        except Exception as exc:
            print(f"[ai] Không tải được YOLO ({exc}). Dùng detector rỗng.")
            self.model = None

    def infer(self, frame: np.ndarray, roi: tuple[float, float, float, float] | None) -> list[Detection]:
        if self.model is None or frame is None:
            return []
        h, w = frame.shape[:2]
        crop = frame
        ox, oy = 0.0, 0.0
        if roi:
            x, y, rw, rh = roi
            x1, y1 = int(x * w), int(y * h)
            x2, y2 = int((x + rw) * w), int((y + rh) * h)
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 > x1 + 4 and y2 > y1 + 4:
                crop = frame[y1:y2, x1:x2]
                ox, oy = x1 / w, y1 / h
        try:
            results = self.model.track(
                crop,
                persist=True,
                conf=self.cfg.conf,
                imgsz=self.cfg.imgsz,
                classes=self.cfg.classes,
                verbose=False,
                device=self.cfg.device,
            )
        except Exception:
            results = self.model.predict(
                crop,
                conf=self.cfg.conf,
                imgsz=self.cfg.imgsz,
                classes=self.cfg.classes,
                verbose=False,
                device=self.cfg.device,
            )
        dets: list[Detection] = []
        if not results:
            return dets
        r = results[0]
        boxes = getattr(r, "boxes", None)
        if boxes is None:
            return dets
        ch, cw = crop.shape[:2]
        for i, b in enumerate(boxes):
            xyxy = b.xyxy[0].tolist()
            cls_id = int(b.cls[0]) if b.cls is not None else 0
            conf = float(b.conf[0]) if b.conf is not None else 0.0
            tid = int(b.id[0]) if getattr(b, "id", None) is not None else i + 1
            bw = max(xyxy[2] - xyxy[0], 1)
            bh = max(xyxy[3] - xyxy[1], 1)
            dets.append(
                Detection(
                    id=tid,
                    cls=CLASS_NAMES.get(cls_id, str(cls_id)),
                    conf=conf,
                    x=ox + xyxy[0] / w,
                    y=oy + xyxy[1] / h,
                    w=bw / w,
                    h=bh / h,
                )
            )
        return dets


def pick_nearest(dets: Sequence[Detection], x: float, y: float) -> Detection | None:
    best = None
    best_d = 1e9
    for d in dets:
        cx = d.x + d.w / 2
        cy = d.y + d.h / 2
        dist = (cx - x) ** 2 + (cy - y) ** 2
        inside = d.x <= x <= d.x + d.w and d.y <= y <= d.y + d.h
        score = dist * (0.15 if inside else 1.0)
        if score < best_d:
            best_d = score
            best = d
    return best


def keep_track(dets: Sequence[Detection], track_id: int | None) -> Detection | None:
    if track_id is None:
        return None
    for d in dets:
        if d.id == track_id:
            return d
    return None
