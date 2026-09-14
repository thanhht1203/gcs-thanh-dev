import { useStore } from "../store";
import { send } from "../ws";

export function CameraPanel() {
  const tel = useStore((s) => s.telemetry);
  const cam = tel.camera;

  return (
    <section className="panel">
      <h3>CAMERA</h3>
      <div className="row">
        <button onClick={() => send({ type: "zoom", action: "out" })}>Zoom −</button>
        <span className="mono">{tel.zoom.toFixed(1)}×</span>
        <button onClick={() => send({ type: "zoom", action: "in" })}>Zoom +</button>
      </div>
      <label>
        Zoom
        <input
          type="range"
          min={1}
          max={30}
          step={0.1}
          value={tel.zoom}
          onChange={(e) => send({ type: "zoom", action: "set", value: Number(e.target.value) })}
        />
      </label>
      <label>
        Độ sáng {cam.brightness}
        <input
          type="range"
          min={0}
          max={100}
          value={cam.brightness}
          onChange={(e) => send({ type: "camera", brightness: Number(e.target.value) })}
        />
      </label>
      <label>
        Tương phản {cam.contrast}
        <input
          type="range"
          min={0}
          max={100}
          value={cam.contrast}
          onChange={(e) => send({ type: "camera", contrast: Number(e.target.value) })}
        />
      </label>
      <div className="row">
        <button
          className={cam.autofocus ? "on" : ""}
          onClick={() => send({ type: "camera", autofocus: !cam.autofocus })}
        >
          Auto focus
        </button>
        <select
          value={cam.quality}
          onChange={(e) => send({ type: "camera", quality: e.target.value, fps: e.target.value === "1080p" ? 10 : 15 })}
        >
          <option value="1080p">Full HD 1080p</option>
          <option value="720p">HD 720p</option>
          <option value="480p">480p</option>
        </select>
      </div>
      <p className="hint">1080p giảm fps trên Jetson để giữ AI. +/- zoom.</p>
    </section>
  );
}
