import { useCallback, useRef, useState } from "react";
import { useStore } from "../store";
import { send } from "../ws";

type Props = {
  src: string | null;
  thermal?: boolean;
  interactive?: boolean;
  label: string;
};

export function VideoStage({ src, thermal, interactive, label }: Props) {
  const tel = useStore((s) => s.telemetry);
  const mode = useStore((s) => s.pointerMode);
  const wrap = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number } | null>(null);
  const [box, setBox] = useState<{ x: number; y: number; w: number; h: number } | null>(null);

  const norm = (e: React.PointerEvent) => {
    const r = wrap.current!.getBoundingClientRect();
    return {
      x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)),
      y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)),
    };
  };

  const onDown = useCallback(
    (e: React.PointerEvent) => {
      if (!interactive) return;
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
      const p = norm(e);
      drag.current = p;
      setBox({ x: p.x, y: p.y, w: 0, h: 0 });
    },
    [interactive]
  );

  const onMove = useCallback(
    (e: React.PointerEvent) => {
      if (!drag.current || !interactive) return;
      const p = norm(e);
      const x = Math.min(drag.current.x, p.x);
      const y = Math.min(drag.current.y, p.y);
      setBox({ x, y, w: Math.abs(p.x - drag.current.x), h: Math.abs(p.y - drag.current.y) });
    },
    [interactive]
  );

  const onUp = useCallback(
    (e: React.PointerEvent) => {
      if (!interactive || !drag.current) return;
      const p = norm(e);
      const w = Math.abs(p.x - drag.current.x);
      const h = Math.abs(p.y - drag.current.y);
      const x = Math.min(drag.current.x, p.x);
      const y = Math.min(drag.current.y, p.y);
      drag.current = null;
      setBox(null);
      if (mode === "roi" && w > 0.02 && h > 0.02) {
        send({ type: "track", action: "roi", x, y, w, h });
      } else {
        send({ type: "track", action: "click", x: p.x, y: p.y });
      }
    },
    [interactive, mode]
  );

  const dets = tel.detections || [];
  const roi = tel.roi;

  return (
    <div
      className={`stage ${thermal ? "ir" : "vis"}`}
      ref={wrap}
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
    >
      {src ? <img src={src} alt={label} draggable={false} /> : <div className="no-sig">KHÔNG CÓ TÍN HIỆU</div>}
      <svg className="overlay" viewBox="0 0 1000 1000" preserveAspectRatio="none">
        <line x1="500" y1="40" x2="500" y2="960" className="cross" />
        <line x1="40" y1="500" x2="960" y2="500" className="cross" />
        <rect x="460" y="460" width="80" height="80" className="cross-box" />
        {dets.map((d) => {
          const tracked = tel.track_on && tel.track_id === d.id;
          return (
            <g key={d.id}>
              <rect
                x={d.x * 1000}
                y={d.y * 1000}
                width={d.w * 1000}
                height={d.h * 1000}
                className={tracked ? "box track" : "box det"}
              />
              <text x={d.x * 1000 + 4} y={d.y * 1000 - 8} className={tracked ? "lbl track" : "lbl"}>
                {d.cls} {Math.round(d.conf * 100)} {tracked ? "● BÁM" : ""}
              </text>
            </g>
          );
        })}
        {roi && (
          <rect
            x={roi[0] * 1000}
            y={roi[1] * 1000}
            width={roi[2] * 1000}
            height={roi[3] * 1000}
            className="box roi"
          />
        )}
        {box && (
          <rect x={box.x * 1000} y={box.y * 1000} width={box.w * 1000} height={box.h * 1000} className="box drag" />
        )}
      </svg>
      <div className="hud tl">
        <span>{label}</span>
        <span>
          ZOOM {tel.zoom.toFixed(1)}× · FOV {tel.fov_h.toFixed(0)}°
        </span>
      </div>
      <div className="hud tr">
        <span>
          PAN {tel.pan.toFixed(1)}° · TILT {tel.tilt.toFixed(1)}°
        </span>
        <span>HDG {tel.heading.toFixed(0)}°</span>
      </div>
      <div className="hud bl">
        <span className={tel.laser_valid ? "ok" : "dim"}>
          LRF {tel.laser_valid && tel.laser_m != null ? `${tel.laser_m.toFixed(1)} m` : "---"}
        </span>
      </div>
      <div className="hud br">
        {tel.sim ? <span className="warn">SIM</span> : <span className="ok">LIVE</span>}
        {tel.recording ? <span className="rec">● REC</span> : null}
      </div>
    </div>
  );
}
