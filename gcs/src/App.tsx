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
  const thermalSolo = useStore((s) => s.thermalSolo);
  const setThermalSolo = useStore((s) => s.setThermalSolo);
  const [draft, setDraft] = useState(url);

  useEffect(() => {
    setDraft(url);
  }, [url]);

  const mainSrc = main === "visible" ? vis : ir;
  const showThermalPip = main === "visible" && layout.showPip;
  const showVisiblePip = main === "thermal" && !thermalSolo;

  const goVisible = (withPip = true) => {
    setMain("visible");
    setThermalSolo(false);
    send({ type: "view", main: "visible" });
    if (withPip && !layout.showPip) useStore.getState().setLayout({ showPip: true });
  };

  /** Ảnh nhiệt full + vẫn hiện PiP ảnh thường để quay lại. */
  const goThermalWithPip = () => {
    setMain("thermal");
    setThermalSolo(false);
    send({ type: "view", main: "thermal" });
  };

  /** Chỉ ảnh nhiệt — không đè ảnh thường. */
  const goThermalOnly = () => {
    setMain("thermal");
    setThermalSolo(true);
    send({ type: "view", main: "thermal" });
  };

  const hideThermal = () => {
    useStore.getState().setLayout({ showPip: false });
    if (main === "thermal") goVisible(false);
  };

  const showThermal = () => {
    useStore.getState().setLayout({ showPip: true });
    if (main !== "visible") goVisible(true);
  };

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
          <div className="stage-wrap">
            <VideoStage
              src={mainSrc}
              thermal={main === "thermal"}
              interactive
              label={main === "visible" ? "ẢNH THƯỜNG" : "ẢNH NHIỆT"}
            />
            {showThermalPip && (
              <div className="view-pip">
                <div
                  className="view-pip-frame"
                  title="Phóng to ảnh nhiệt (còn PiP ảnh thường)"
                  role="button"
                  tabIndex={0}
                  onClick={goThermalWithPip}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      goThermalWithPip();
                    }
                  }}
                >
                  <VideoStage src={ir} thermal compact label="ẢNH NHIỆT" />
                </div>
                <div className="view-pip-bar">
                  <button type="button" onClick={goThermalWithPip}>
                    Phóng to
                  </button>
                  <button type="button" onClick={goThermalOnly}>
                    Chỉ nhiệt
                  </button>
                  <button type="button" onClick={hideThermal}>
                    Tắt
                  </button>
                </div>
              </div>
            )}
            {showVisiblePip && (
              <div className="view-pip">
                <div
                  className="view-pip-frame"
                  title="Quay lại ảnh thường"
                  role="button"
                  tabIndex={0}
                  onClick={() => goVisible(true)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      goVisible(true);
                    }
                  }}
                >
                  <VideoStage src={vis} compact label="ẢNH THƯỜNG" />
                </div>
                <div className="view-pip-bar">
                  <button type="button" className="on" onClick={() => goVisible(true)}>
                    ← Ảnh thường
                  </button>
                  <button type="button" onClick={goThermalOnly}>
                    Chỉ nhiệt
                  </button>
                </div>
              </div>
            )}
            {main === "thermal" && thermalSolo && (
              <div className="thermal-solo-bar">
                <button type="button" className="on" onClick={() => goVisible(true)}>
                  ← Ảnh thường
                </button>
                <button type="button" onClick={goThermalWithPip}>
                  Hiện PiP thường
                </button>
              </div>
            )}
          </div>
          {layout.showMap && (
            <div className="bottom">
              <MapPanel />
            </div>
          )}
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
        <button className={`ghost${main === "visible" ? " on" : ""}`} onClick={() => goVisible(true)}>
          1 Ảnh thường
        </button>
        {layout.showPip || main === "thermal" ? (
          <button className="ghost" onClick={hideThermal}>
            Tắt nhiệt
          </button>
        ) : (
          <button className="ghost" onClick={showThermal}>
            Hiện nhiệt
          </button>
        )}
        <button
          className={`ghost${main === "thermal" && !thermalSolo ? " on" : ""}`}
          onClick={goThermalWithPip}
          title="Ảnh nhiệt lớn + PiP ảnh thường"
        >
          2 Nhiệt + PiP
        </button>
        <button
          className={`ghost${main === "thermal" && thermalSolo ? " on" : ""}`}
          onClick={goThermalOnly}
          title="Chỉ ảnh nhiệt, không đè ảnh thường"
        >
          3 Chỉ nhiệt
        </button>
      </footer>

      <SettingsModal />
    </div>
  );
}
