import { useState } from "react";
import { useStore } from "../store";
import { send } from "../ws";

export function PtzPanel() {
  const tel = useStore((s) => s.telemetry);
  const [pan, setPan] = useState("");
  const [tilt, setTilt] = useState("");

  const hold = (p: number, t: number) => {
    send({ type: "ptz", action: "nudge", pan: p, tilt: t, speed: 1 });
  };
  const stop = () => send({ type: "ptz", action: "stop" });

  return (
    <section className="panel">
      <h3>BỆ QUAY · PAN / TILT</h3>
      <div className="ptz-grid">
        <i />
        <button onMouseDown={() => hold(0, 1)} onMouseUp={stop} onMouseLeave={stop}>
          ↑
        </button>
        <i />
        <button onMouseDown={() => hold(-1, 0)} onMouseUp={stop} onMouseLeave={stop}>
          ←
        </button>
        <button className="home" onClick={() => send({ type: "ptz", action: "home" })}>
          HOME
        </button>
        <button onMouseDown={() => hold(1, 0)} onMouseUp={stop} onMouseLeave={stop}>
          →
        </button>
        <i />
        <button onMouseDown={() => hold(0, -1)} onMouseUp={stop} onMouseLeave={stop}>
          ↓
        </button>
        <i />
      </div>
      <label>
        Pan {tel.pan.toFixed(1)}°
        <input
          type="range"
          min={-180}
          max={180}
          step={0.5}
          value={tel.pan}
          onChange={(e) => send({ type: "ptz", action: "slider", pan: Number(e.target.value), tilt: tel.tilt })}
        />
      </label>
      <label>
        Tilt {tel.tilt.toFixed(1)}°
        <input
          type="range"
          min={-45}
          max={45}
          step={0.5}
          value={tel.tilt}
          onChange={(e) => send({ type: "ptz", action: "slider", pan: tel.pan, tilt: Number(e.target.value) })}
        />
      </label>
      <div className="row">
        <input placeholder="Pan °" value={pan} onChange={(e) => setPan(e.target.value)} />
        <input placeholder="Tilt °" value={tilt} onChange={(e) => setTilt(e.target.value)} />
        <button
          onClick={() =>
            send({ type: "ptz", action: "goto", pan: Number(pan || 0), tilt: Number(tilt || 0) })
          }
        >
          GOTO
        </button>
      </div>
      <p className="hint">Phím: WASD / mũi tên · H = Home</p>
    </section>
  );
}
