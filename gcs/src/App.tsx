import { useEffect, useState } from "react";
import { VideoStage } from "./components/VideoStage";
import { MapPanel } from "./components/MapPanel";
import { PtzPanel } from "./components/PtzPanel";
import { CameraPanel } from "./components/CameraPanel";
import { AiPanel } from "./components/AiPanel";
import { RecordPanel } from "./components/RecordPanel";
import { SettingsModal } from "./components/SettingsModal";
import { useHotkeys } from "./hooks/useHotkeys";
import { useStore } from "./store";
import { send, useJetsonSocket } from "./ws";
import "./App.css";

export default function App() {
  useJetsonSocket();
  useHotkeys();
  const connected = useStore((s) => s.connected);
  const url = useStore((s) => s.url);
  const setUrl = useStore((s) => s.setUrl);
  const reconnect = useStore((s) => s.reconnect);
  const layout = useStore((s) => s.layout);
  const setSettingsOpen = useStore((s) => s.setSettingsOpen);
  const tel = useStore((s) => s.telemetry);
  const vis = useStore((s) => s.visibleUrl);
  const ir = useStore((s) => s.thermalUrl);
  const main = useStore((s) => s.mainView);
  const setMain = useStore((s) => s.setMainView);
  const [draft, setDraft] = useState(url);

  useEffect(() => {
    setDraft(url);
  }, [url]);

  const mainSrc = main === "visible" ? vis : ir;
  const pipSrc = main === "visible" ? ir : vis;

  return (
    <div
      className="app"
      style={
        {
          "--sidebar-w": `${layout.sidebarWidth}px`,
          "--bottom-h": `${layout.bottomHeight}px`,
        } as React.CSSProperties
      }
    >
      <header className="top">
        <div className="brand">
          <span className="mark" />
          EO CONTROL
          <small>GCS · Jetson Orin Nano</small>
        </div>
        <div className="conn">
          <span className={`dot ${connected ? "on" : ""}`} />
          {connected ? "Kết nối" : "Mất kết nối"}
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => {
              const next = draft.trim();
              if (next && next !== url) setUrl(next);
              else setDraft(url);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                const next = draft.trim();
                if (next) setUrl(next);
              }
            }}
          />
          <button
            type="button"
            className="ghost"
            title="Kết nối lại"
            onClick={() => {
              const next = draft.trim() || url;
              setDraft(next);
              if (next !== url) setUrl(next);
              else reconnect();
            }}
          >
            Reconnect
          </button>
          <button type="button" className="ghost" onClick={() => setSettingsOpen(true)} title="Cấu hình">
            Cấu hình
          </button>
        </div>
        <div className="chips">
          <span>{tel.gps.fix ? `GPS ${tel.gps.lat.toFixed(5)} ${tel.gps.lon.toFixed(5)}` : "GPS --"}</span>
          <span>ALT {tel.gps.alt.toFixed(0)} m</span>
          <span>HDG {tel.heading.toFixed(0)}°</span>
          <span className={tel.recording ? "rec" : ""}>{tel.recording ? "REC" : tel.camera.quality}</span>
        </div>
      </header>

      <div className="body">
        <div className="col-main">
          <VideoStage
            src={mainSrc}
            thermal={main === "thermal"}
            interactive
            label={main === "visible" ? "ẢNH THƯỜNG" : "ẢNH NHIỆT"}
          />
          <div className="bottom">
            {layout.showPip && (
              <div className="pip" onClick={() => setMain(main === "visible" ? "thermal" : "visible")}>
                <VideoStage
                  src={pipSrc}
                  thermal={main === "visible"}
                  label={main === "visible" ? "ẢNH NHIỆT" : "ẢNH THƯỜNG"}
                />
              </div>
            )}
            {layout.showMap && <MapPanel />}
          </div>
        </div>
        <aside className="col-side">
          <PtzPanel />
          <CameraPanel />
          <AiPanel />
          <RecordPanel />
        </aside>
      </div>

      <footer className="status">
        <span>PAN {tel.pan.toFixed(1)}°</span>
        <span>TILT {tel.tilt.toFixed(1)}°</span>
        <span>ZOOM {tel.zoom.toFixed(1)}×</span>
        <span>LRF {tel.laser_valid && tel.laser_m != null ? `${tel.laser_m.toFixed(1)} m` : "---"}</span>
        <span>
          MT{" "}
          {tel.target_geo.valid
            ? `${tel.target_geo.lat.toFixed(5)}, ${tel.target_geo.lon.toFixed(5)}`
            : "---"}
        </span>
        <span>{tel.detections.length} mục tiêu</span>
        <span className="grow" />
        <button
          className="ghost"
          onClick={() => {
            setMain("visible");
            send({ type: "view", main: "visible" });
          }}
        >
          1 Ảnh thường
        </button>
        <button
          className="ghost"
          onClick={() => {
            setMain("thermal");
            send({ type: "view", main: "thermal" });
          }}
        >
          2 Ảnh nhiệt
        </button>
      </footer>

      <SettingsModal />
    </div>
  );
}
