import { useStore } from "../store";
import { send } from "../ws";

const CLS: Record<string, string> = {
  person: "Người",
  car: "Xe",
  truck: "Xe tải",
  motorcycle: "Xe máy",
  bicycle: "Xe đạp",
  bus: "Xe buýt",
};

export function AiPanel() {
  const tel = useStore((s) => s.telemetry);
  const mode = useStore((s) => s.pointerMode);
  const setMode = useStore((s) => s.setPointerMode);

  return (
    <section className="panel">
      <h3>PHÁT HIỆN · BÁM MỤC TIÊU</h3>
      <div className="row">
        <button
          className={tel.detect_on ? "on" : ""}
          onClick={() => send({ type: "detect", enabled: !tel.detect_on })}
        >
          Phát hiện {tel.detect_on ? "ON" : "OFF"}
        </button>
        <button className={tel.track_on ? "on warn" : ""} onClick={() => send({ type: "track", action: "nearest" })}>
          Bám tâm
        </button>
        <button onClick={() => send({ type: "track", action: "stop" })}>Dừng bám</button>
      </div>
      <div className="row">
        <button className={mode === "track" ? "on" : ""} onClick={() => setMode("track")}>
          Click chọn
        </button>
        <button className={mode === "roi" ? "on" : ""} onClick={() => setMode("roi")}>
          Khoanh vùng
        </button>
      </div>
      <p className="hint">
        Click trên video để bám. Kéo chuột (chế độ khoanh vùng) để tìm trong ROI. T = bám gần tâm, Esc = dừng.
      </p>
      <ul className="dets">
        {tel.detections.slice(0, 8).map((d) => (
          <li
            key={d.id}
            className={tel.track_id === d.id ? "active" : ""}
            onClick={() => send({ type: "track", action: "click", x: d.x + d.w / 2, y: d.y + d.h / 2 })}
          >
            <b>{CLS[d.cls] || d.cls}</b>
            <span>#{d.id}</span>
            <span>{Math.round(d.conf * 100)}%</span>
          </li>
        ))}
        {tel.detections.length === 0 && <li className="dim">Không có mục tiêu</li>}
      </ul>
    </section>
  );
}
