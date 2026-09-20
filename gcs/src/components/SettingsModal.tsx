import { useEffect, useMemo, useState } from "react";
import { useStore, type GcsLayout } from "../store";
import { requestConfig } from "../ws";

type Tab = "gcs" | "service" | "platform" | "cameras" | "serial" | "ai" | "optics";

function deepSet(obj: Record<string, unknown>, path: string, value: unknown) {
  const parts = path.split(".");
  const next = structuredClone(obj);
  let cur: Record<string, unknown> = next;
  for (let i = 0; i < parts.length - 1; i++) {
    const key = parts[i];
    const child = cur[key];
    if (!child || typeof child !== "object" || Array.isArray(child)) {
      cur[key] = {};
    }
    cur = cur[key] as Record<string, unknown>;
  }
  cur[parts[parts.length - 1]] = value;
  return next;
}

function getPath(obj: Record<string, unknown>, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, key) => {
    if (acc && typeof acc === "object" && !Array.isArray(acc)) {
      return (acc as Record<string, unknown>)[key];
    }
    return undefined;
  }, obj);
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="cfg-field">
      <span>{label}</span>
      {children}
    </label>
  );
}

export function SettingsModal() {
  const open = useStore((s) => s.settingsOpen);
  const setOpen = useStore((s) => s.setSettingsOpen);
  const url = useStore((s) => s.url);
  const setUrl = useStore((s) => s.setUrl);
  const layout = useStore((s) => s.layout);
  const setLayout = useStore((s) => s.setLayout);
  const setMainView = useStore((s) => s.setMainView);
  const connected = useStore((s) => s.connected);
  const setConfigStatus = useStore((s) => s.setConfigStatus);

  const [tab, setTab] = useState<Tab>("gcs");
  const [urlDraft, setUrlDraft] = useState(url);
  const [layoutDraft, setLayoutDraft] = useState<GcsLayout>(layout);
  const [draft, setDraft] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  // Chỉ load khi mở modal — không phụ thuộc jetsonConfig/layout (tránh reset checkbox/draft).
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setUrlDraft(useStore.getState().url);
    setLayoutDraft(useStore.getState().layout);
    setMsg(null);
    setDraft(null);

    if (!useStore.getState().connected) {
      setMsg("Chưa kết nối Jetson — vẫn lưu được tab GCS.");
      return;
    }

    setBusy(true);
    requestConfig("get")
      .then((res) => {
        if (cancelled) return;
        setDraft((res.config as Record<string, unknown>) || {});
      })
      .catch((e: Error) => {
        if (!cancelled) setMsg(e.message);
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open]);

  const setVal = (path: string, value: unknown) => {
    setDraft((prev) => (prev ? deepSet(prev, path, value) : prev));
  };

  const str = (path: string) => String(getPath(draft || {}, path) ?? "");
  const num = (path: string) => Number(getPath(draft || {}, path) ?? 0);
  const bool = (path: string) => Boolean(getPath(draft || {}, path));

  const tabs = useMemo(
    () =>
      [
        ["gcs", "GCS"],
        ["service", "Service"],
        ["platform", "Platform"],
        ["cameras", "Camera"],
        ["serial", "Serial"],
        ["ai", "AI"],
        ["optics", "Optics"],
      ] as const,
    [],
  );

  if (!open) return null;

  const saveGcs = () => {
    setUrl(urlDraft.trim());
    setLayout(layoutDraft);
    setMainView(layoutDraft.defaultMainView);
    setMsg("Đã lưu cấu hình GCS (localStorage)");
    setConfigStatus("GCS đã lưu");
  };

  const applyJetson = async () => {
    if (!draft) {
      setMsg("Chưa có config Jetson");
      return;
    }
    if (!connected) {
      setMsg("Chưa kết nối Jetson");
      return;
    }
    setSaving(true);
    setMsg(null);
    try {
      const res = await requestConfig("set", draft, true);
      const next = (res.config as Record<string, unknown>) || draft;
      setDraft(next);
      const warns = (res.warnings as string[] | undefined) || [];
      const errs = (res.errors as string[] | undefined) || [];
      if (res.ok === false || errs.length) {
        setMsg(String(res.error || errs.join("; ") || "Lỗi apply config"));
        setConfigStatus("Jetson config lỗi");
      } else {
        setMsg(`Đã lưu & hot-apply${warns.length ? " — " + warns.join("; ") : ""}`);
        setConfigStatus("Jetson config đã apply");
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={() => setOpen(false)}>
      <div className="modal settings-modal" onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <h2>CẤU HÌNH</h2>
          <button type="button" className="ghost" onClick={() => setOpen(false)}>
            Đóng
          </button>
        </header>

        <div className="settings-tabs">
          {tabs.map(([id, label]) => (
            <button
              type="button"
              key={id}
              className={tab === id ? "on" : ""}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="settings-body">
          {tab === "gcs" && (
            <div className="cfg-grid">
              <Field label="WebSocket URL">
                <input value={urlDraft} onChange={(e) => setUrlDraft(e.target.value)} />
              </Field>
              <Field label="Độ rộng sidebar (px)">
                <input
                  type="number"
                  min={260}
                  max={480}
                  value={layoutDraft.sidebarWidth}
                  onChange={(e) =>
                    setLayoutDraft({ ...layoutDraft, sidebarWidth: Number(e.target.value) || 320 })
                  }
                />
              </Field>
              <Field label="Chiều cao hàng dưới (px)">
                <input
                  type="number"
                  min={160}
                  max={420}
                  value={layoutDraft.bottomHeight}
                  onChange={(e) =>
                    setLayoutDraft({ ...layoutDraft, bottomHeight: Number(e.target.value) || 240 })
                  }
                />
              </Field>
              <Field label="Màn hình chính mặc định">
                <select
                  value={layoutDraft.defaultMainView}
                  onChange={(e) =>
                    setLayoutDraft({
                      ...layoutDraft,
                      defaultMainView: e.target.value as "visible" | "thermal",
                    })
                  }
                >
                  <option value="visible">Ảnh thường</option>
                  <option value="thermal">Ảnh nhiệt</option>
                </select>
              </Field>
              <label className="cfg-check">
                <input
                  type="checkbox"
                  checked={layoutDraft.showPip}
                  onChange={(e) => setLayoutDraft({ ...layoutDraft, showPip: e.target.checked })}
                />
                Hiện PiP camera phụ
              </label>
              <label className="cfg-check">
                <input
                  type="checkbox"
                  checked={layoutDraft.showMap}
                  onChange={(e) => setLayoutDraft({ ...layoutDraft, showMap: e.target.checked })}
                />
                Hiện bản đồ
              </label>
              <p className="hint">Cấu hình GCS lưu trên máy này (localStorage), không gửi lên Jetson.</p>
            </div>
          )}

          {tab !== "gcs" && busy && <p className="hint">Đang tải config từ Jetson…</p>}
          {tab !== "gcs" && !busy && !draft && (
            <p className="hint">
              {connected ? "Không có dữ liệu config" : "Cần kết nối Jetson để sửa config thiết bị."}
            </p>
          )}

          {tab === "service" && draft && (
            <div className="cfg-grid">
              <Field label="Host lắng nghe">
                <input value={str("host")} onChange={(e) => setVal("host", e.target.value)} />
              </Field>
              <Field label="Port">
                <input type="number" value={num("port")} onChange={(e) => setVal("port", Number(e.target.value))} />
              </Field>
              <label className="cfg-check">
                <input type="checkbox" checked={bool("sim")} onChange={(e) => setVal("sim", e.target.checked)} />
                Chế độ sim
              </label>
              <p className="hint">Đổi host/port chỉ có hiệu lực sau khi restart service Jetson.</p>
            </div>
          )}

          {tab === "platform" && draft && (
            <div className="cfg-grid">
              <Field label="Vai trò">
                <select value={str("platform.role")} onChange={(e) => setVal("platform.role", e.target.value)}>
                  <option value="mast">mast</option>
                  <option value="uav">uav</option>
                </select>
              </Field>
              <Field label="Chiều cao (m)">
                <input
                  type="number"
                  step="0.1"
                  value={num("platform.height_m")}
                  onChange={(e) => setVal("platform.height_m", Number(e.target.value))}
                />
              </Field>
              <Field label="Lat mặc định">
                <input
                  type="number"
                  step="0.0001"
                  value={num("platform.default_lat")}
                  onChange={(e) => setVal("platform.default_lat", Number(e.target.value))}
                />
              </Field>
              <Field label="Lon mặc định">
                <input
                  type="number"
                  step="0.0001"
                  value={num("platform.default_lon")}
                  onChange={(e) => setVal("platform.default_lon", Number(e.target.value))}
                />
              </Field>
              <Field label="Alt mặc định (m)">
                <input
                  type="number"
                  value={num("platform.default_alt")}
                  onChange={(e) => setVal("platform.default_alt", Number(e.target.value))}
                />
              </Field>
              <Field label="Heading mặc định">
                <input
                  type="number"
                  value={num("platform.default_heading")}
                  onChange={(e) => setVal("platform.default_heading", Number(e.target.value))}
                />
              </Field>
            </div>
          )}

          {tab === "cameras" && draft && (
            <div className="cfg-grid">
              <h4>Ảnh thường</h4>
              <Field label="Device / index">
                <input
                  value={str("cameras.visible.device")}
                  onChange={(e) => {
                    const v = e.target.value;
                    setVal("cameras.visible.device", /^\d+$/.test(v) ? Number(v) : v);
                  }}
                />
              </Field>
              <Field label="Backend">
                <select
                  value={str("cameras.visible.backend")}
                  onChange={(e) => setVal("cameras.visible.backend", e.target.value)}
                >
                  <option value="auto">auto</option>
                  <option value="dshow">dshow</option>
                  <option value="v4l2">v4l2</option>
                  <option value="any">any</option>
                </select>
              </Field>
              <Field label="Width">
                <input
                  type="number"
                  value={num("cameras.visible.width")}
                  onChange={(e) => setVal("cameras.visible.width", Number(e.target.value))}
                />
              </Field>
              <Field label="Height">
                <input
                  type="number"
                  value={num("cameras.visible.height")}
                  onChange={(e) => setVal("cameras.visible.height", Number(e.target.value))}
                />
              </Field>
              <Field label="FPS">
                <input
                  type="number"
                  value={num("cameras.visible.fps")}
                  onChange={(e) => setVal("cameras.visible.fps", Number(e.target.value))}
                />
              </Field>
              <Field label="RTSP (tuỳ chọn)">
                <input
                  value={str("cameras.visible.rtsp") === "null" ? "" : str("cameras.visible.rtsp")}
                  onChange={(e) => setVal("cameras.visible.rtsp", e.target.value || null)}
                />
              </Field>

              <h4>Ảnh nhiệt</h4>
              <Field label="Device / index">
                <input
                  value={str("cameras.thermal.device")}
                  onChange={(e) => {
                    const v = e.target.value;
                    setVal("cameras.thermal.device", /^\d+$/.test(v) ? Number(v) : v);
                  }}
                />
              </Field>
              <Field label="Backend">
                <select
                  value={str("cameras.thermal.backend")}
                  onChange={(e) => setVal("cameras.thermal.backend", e.target.value)}
                >
                  <option value="auto">auto</option>
                  <option value="dshow">dshow</option>
                  <option value="v4l2">v4l2</option>
                  <option value="any">any</option>
                </select>
              </Field>
              <Field label="Width">
                <input
                  type="number"
                  value={num("cameras.thermal.width")}
                  onChange={(e) => setVal("cameras.thermal.width", Number(e.target.value))}
                />
              </Field>
              <Field label="Height">
                <input
                  type="number"
                  value={num("cameras.thermal.height")}
                  onChange={(e) => setVal("cameras.thermal.height", Number(e.target.value))}
                />
              </Field>
              <Field label="FPS">
                <input
                  type="number"
                  value={num("cameras.thermal.fps")}
                  onChange={(e) => setVal("cameras.thermal.fps", Number(e.target.value))}
                />
              </Field>
              <label className="cfg-check">
                <input
                  type="checkbox"
                  checked={bool("cameras.thermal.colormap")}
                  onChange={(e) => setVal("cameras.thermal.colormap", e.target.checked)}
                />
                Colormap nhiệt
              </label>
              <Field label="RTSP (tuỳ chọn)">
                <input
                  value={str("cameras.thermal.rtsp") === "null" ? "" : str("cameras.thermal.rtsp")}
                  onChange={(e) => setVal("cameras.thermal.rtsp", e.target.value || null)}
                />
              </Field>
            </div>
          )}

          {tab === "serial" && draft && (
            <div className="cfg-grid">
              <p className="hint" style={{ gridColumn: "1 / -1" }}>
                Cùng kiểu field: Protocol → Port → Baud → Parity/Address → tham số riêng. Jetson: /dev/ttyUSB* ·
                Windows: COMx.
              </p>

              <h4>VISCA (ảnh thường FCB-EV9520L)</h4>
              <Field label="Protocol">
                <select value={str("visca.protocol") || "visca"} onChange={(e) => setVal("visca.protocol", e.target.value)}>
                  <option value="visca">visca</option>
                  <option value="sim">sim</option>
                </select>
              </Field>
              <Field label="Port">
                <input value={str("visca.port")} onChange={(e) => setVal("visca.port", e.target.value)} />
              </Field>
              <Field label="Baud">
                <input type="number" value={num("visca.baud")} onChange={(e) => setVal("visca.baud", Number(e.target.value))} />
              </Field>
              <Field label="Parity">
                <select value={str("visca.parity") || "none"} onChange={(e) => setVal("visca.parity", e.target.value)}>
                  <option value="none">none</option>
                  <option value="even">even</option>
                  <option value="odd">odd</option>
                </select>
              </Field>
              <Field label="Address">
                <input
                  type="number"
                  min={1}
                  max={7}
                  value={num("visca.address") || 1}
                  onChange={(e) => setVal("visca.address", Number(e.target.value))}
                />
              </Field>
              <Field label="Pulse stop (s)">
                <input
                  type="number"
                  step="0.05"
                  value={num("visca.zoom_pulse_s")}
                  onChange={(e) => setVal("visca.zoom_pulse_s", Number(e.target.value))}
                />
              </Field>

              <h4>SATIS (ảnh nhiệt)</h4>
              <Field label="Protocol">
                <select value={str("satis.protocol") || "satis"} onChange={(e) => setVal("satis.protocol", e.target.value)}>
                  <option value="satis">satis</option>
                  <option value="sim">sim</option>
                </select>
              </Field>
              <Field label="Port">
                <input value={str("satis.port")} onChange={(e) => setVal("satis.port", e.target.value)} />
              </Field>
              <Field label="Baud">
                <input type="number" value={num("satis.baud")} onChange={(e) => setVal("satis.baud", Number(e.target.value))} />
              </Field>
              <Field label="Parity">
                <select value={str("satis.parity") || "even"} onChange={(e) => setVal("satis.parity", e.target.value)}>
                  <option value="none">none</option>
                  <option value="even">even</option>
                  <option value="odd">odd</option>
                </select>
              </Field>
              <Field label="Zoom speed">
                <input
                  type="number"
                  step="0.1"
                  value={num("satis.zoom_speed")}
                  onChange={(e) => setVal("satis.zoom_speed", Number(e.target.value))}
                />
              </Field>
              <Field label="FOV set point (rad)">
                <input
                  type="number"
                  step="0.01"
                  value={num("satis.fov_set_point")}
                  onChange={(e) => setVal("satis.fov_set_point", Number(e.target.value))}
                />
              </Field>
              <Field label="Pulse stop (s)">
                <input
                  type="number"
                  step="0.05"
                  value={num("satis.zoom_pulse_s")}
                  onChange={(e) => setVal("satis.zoom_pulse_s", Number(e.target.value))}
                />
              </Field>

              <h4>PTZ</h4>
              <Field label="Protocol">
                <select value={str("ptz.protocol")} onChange={(e) => setVal("ptz.protocol", e.target.value)}>
                  <option value="pelco_d">pelco_d</option>
                  <option value="sim">sim</option>
                </select>
              </Field>
              <Field label="Port">
                <input value={str("ptz.port")} onChange={(e) => setVal("ptz.port", e.target.value)} />
              </Field>
              <Field label="Baud">
                <input type="number" value={num("ptz.baud")} onChange={(e) => setVal("ptz.baud", Number(e.target.value))} />
              </Field>
              <Field label="Address">
                <input
                  type="number"
                  value={num("ptz.address")}
                  onChange={(e) => setVal("ptz.address", Number(e.target.value))}
                />
              </Field>
              <Field label="Pan speed">
                <input
                  type="number"
                  step="0.1"
                  value={num("ptz.pan_speed")}
                  onChange={(e) => setVal("ptz.pan_speed", Number(e.target.value))}
                />
              </Field>
              <Field label="Tilt speed">
                <input
                  type="number"
                  step="0.1"
                  value={num("ptz.tilt_speed")}
                  onChange={(e) => setVal("ptz.tilt_speed", Number(e.target.value))}
                />
              </Field>

              <h4>Laser LRF 7047</h4>
              <Field label="Protocol">
                <select value={str("laser.protocol")} onChange={(e) => setVal("laser.protocol", e.target.value)}>
                  <option value="lrf7047">lrf7047</option>
                  <option value="generic">generic</option>
                  <option value="lightware">lightware</option>
                  <option value="sim">sim</option>
                </select>
              </Field>
              <Field label="Port">
                <input value={str("laser.port")} onChange={(e) => setVal("laser.port", e.target.value)} />
              </Field>
              <Field label="Baud">
                <input type="number" value={num("laser.baud")} onChange={(e) => setVal("laser.baud", Number(e.target.value))} />
              </Field>
              <Field label="Parity">
                <select value={str("laser.parity")} onChange={(e) => setVal("laser.parity", e.target.value)}>
                  <option value="none">none</option>
                  <option value="even">even</option>
                  <option value="odd">odd</option>
                </select>
              </Field>
              <Field label="Lệnh đo">
                <input value={str("laser.measure_cmd")} onChange={(e) => setVal("laser.measure_cmd", e.target.value)} />
              </Field>
              <Field label="Chu kỳ continuous (s)">
                <input
                  type="number"
                  step="0.1"
                  value={num("laser.measure_interval_s")}
                  onChange={(e) => setVal("laser.measure_interval_s", Number(e.target.value))}
                />
              </Field>

              <h4>GPS / Compass</h4>
              <Field label="Protocol / source">
                <select value={str("compass.source")} onChange={(e) => setVal("compass.source", e.target.value)}>
                  <option value="gps">gps</option>
                  <option value="serial">serial</option>
                  <option value="sim">sim</option>
                </select>
              </Field>
              <Field label="GPS port">
                <input value={str("gps.port")} onChange={(e) => setVal("gps.port", e.target.value)} />
              </Field>
              <Field label="GPS baud">
                <input type="number" value={num("gps.baud")} onChange={(e) => setVal("gps.baud", Number(e.target.value))} />
              </Field>
              <Field label="Compass port">
                <input value={str("compass.port")} onChange={(e) => setVal("compass.port", e.target.value)} />
              </Field>
              <Field label="Compass baud">
                <input
                  type="number"
                  value={num("compass.baud")}
                  onChange={(e) => setVal("compass.baud", Number(e.target.value))}
                />
              </Field>
            </div>
          )}

          {tab === "ai" && draft && (
            <div className="cfg-grid">
              <Field label="Model">
                <input value={str("ai.model")} onChange={(e) => setVal("ai.model", e.target.value)} />
              </Field>
              <Field label="Device">
                <input
                  value={str("ai.device")}
                  onChange={(e) => {
                    const v = e.target.value;
                    setVal("ai.device", /^\d+$/.test(v) ? Number(v) : v);
                  }}
                />
              </Field>
              <Field label="Confidence">
                <input
                  type="number"
                  step="0.05"
                  min={0}
                  max={1}
                  value={num("ai.conf")}
                  onChange={(e) => setVal("ai.conf", Number(e.target.value))}
                />
              </Field>
              <Field label="imgsz">
                <input type="number" value={num("ai.imgsz")} onChange={(e) => setVal("ai.imgsz", Number(e.target.value))} />
              </Field>
              <Field label="Classes (CSV)">
                <input
                  value={((getPath(draft, "ai.classes") as number[]) || []).join(",")}
                  onChange={(e) =>
                    setVal(
                      "ai.classes",
                      e.target.value
                        .split(",")
                        .map((x) => x.trim())
                        .filter(Boolean)
                        .map(Number),
                    )
                  }
                />
              </Field>
              <label className="cfg-check">
                <input
                  type="checkbox"
                  checked={bool("ai.use_ultralytics")}
                  onChange={(e) => setVal("ai.use_ultralytics", e.target.checked)}
                />
                Dùng Ultralytics YOLO
              </label>
            </div>
          )}

          {tab === "optics" && draft && (
            <div className="cfg-grid">
              <Field label="FOV ngang @1×">
                <input
                  type="number"
                  step="0.1"
                  value={num("optics.fov_h_1x")}
                  onChange={(e) => setVal("optics.fov_h_1x", Number(e.target.value))}
                />
              </Field>
              <Field label="Zoom min">
                <input
                  type="number"
                  step="0.1"
                  value={num("optics.zoom_min")}
                  onChange={(e) => setVal("optics.zoom_min", Number(e.target.value))}
                />
              </Field>
              <Field label="Zoom max">
                <input
                  type="number"
                  step="0.1"
                  value={num("optics.zoom_max")}
                  onChange={(e) => setVal("optics.zoom_max", Number(e.target.value))}
                />
              </Field>
              <Field label="Thư mục ghi hình">
                <input value={str("record.dir")} onChange={(e) => setVal("record.dir", e.target.value)} />
              </Field>
              <Field label="FourCC">
                <input value={str("record.fourcc")} onChange={(e) => setVal("record.fourcc", e.target.value)} />
              </Field>
            </div>
          )}
        </div>

        <footer className="modal-foot">
          {msg && <span className={msg.includes("Lỗi") || msg.includes("Chưa") ? "hint" : "hint ok"}>{msg}</span>}
          <span className="grow" />
          {tab === "gcs" ? (
            <button type="button" className="on" onClick={saveGcs}>
              Lưu GCS
            </button>
          ) : (
            <button
              type="button"
              className="on"
              onClick={applyJetson}
              disabled={saving || busy || !connected || !draft}
            >
              {saving ? "Đang apply…" : "Lưu & hot-apply Jetson"}
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}
