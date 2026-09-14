import { useStore } from "../store";
import { send } from "../ws";

function download(url: string | null, name: string) {
  if (!url) return;
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
}

export function RecordPanel() {
  const tel = useStore((s) => s.telemetry);
  const vis = useStore((s) => s.visibleUrl);
  const ir = useStore((s) => s.thermalUrl);

  const photo = () => {
    send({ type: "record", action: "photo", save_to: "both" });
    const ts = new Date().toISOString().replace(/[:.]/g, "-");
    download(vis, `eo_vis_${ts}.jpg`);
    download(ir, `eo_ir_${ts}.jpg`);
  };

  return (
    <section className="panel">
      <h3>GHI HÌNH</h3>
      <div className="row">
        <button onClick={photo}>Chụp ảnh</button>
        {tel.recording ? (
          <button className="warn" onClick={() => send({ type: "record", action: "stop" })}>
            Dừng quay
          </button>
        ) : (
          <button onClick={() => send({ type: "record", action: "start" })}>Quay video</button>
        )}
        <button
          onClick={() => send({ type: "laser", action: "once" })}
          title="Đo xa laser"
        >
          Laser
        </button>
      </div>
      <p className="hint">
        Ảnh lưu trên Jetson (`data/recordings`) và tải về PC. Video ghi trên Jetson. Space = chụp.
      </p>
      {tel.last_photo && <p className="hint ok">Jetson: {tel.last_photo.split(/[/\\]/).pop()}</p>}
    </section>
  );
}
