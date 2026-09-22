import { create } from "zustand";
import { emptyTelemetry, type Telemetry } from "./types";

export type PointerMode = "track" | "roi";

/** Chế độ xem mặc định khi mở GCS / sau khi lưu Cấu hình. */
export type DefaultViewMode = "visible" | "thermal_pip" | "thermal_only";

export type GcsLayout = {
  sidebarWidth: number;
  bottomHeight: number;
  /** Khi đang ảnh thường: hiện PiP ảnh nhiệt (~1/6). */
  showPip: boolean;
  showMap: boolean;
  defaultViewMode: DefaultViewMode;
};

const URL_KEY = "eo.ws.url.loopback2";
const LAYOUT_KEY = "eo.gcs.layout";

const defaultLayout = (): GcsLayout => ({
  sidebarWidth: 320,
  bottomHeight: 240,
  showPip: true,
  showMap: true,
  defaultViewMode: "visible",
});

function migrateLayout(raw: Record<string, unknown>): GcsLayout {
  const base = defaultLayout();
  const merged = { ...base, ...raw } as GcsLayout & { defaultMainView?: string };
  if (!raw.defaultViewMode && raw.defaultMainView) {
    merged.defaultViewMode = raw.defaultMainView === "thermal" ? "thermal_pip" : "visible";
  }
  if (merged.defaultViewMode !== "visible" && merged.defaultViewMode !== "thermal_pip" && merged.defaultViewMode !== "thermal_only") {
    merged.defaultViewMode = "visible";
  }
  delete (merged as { defaultMainView?: string }).defaultMainView;
  return {
    sidebarWidth: Number(merged.sidebarWidth) || base.sidebarWidth,
    bottomHeight: Number(merged.bottomHeight) || base.bottomHeight,
    showPip: merged.showPip !== false,
    showMap: merged.showMap !== false,
    defaultViewMode: merged.defaultViewMode,
  };
}

function loadLayout(): GcsLayout {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY);
    if (!raw) return defaultLayout();
    return migrateLayout(JSON.parse(raw) as Record<string, unknown>);
  } catch {
    return defaultLayout();
  }
}

export function viewModeToState(mode: DefaultViewMode): {
  mainView: "visible" | "thermal";
  thermalSolo: boolean;
} {
  if (mode === "thermal_only") return { mainView: "thermal", thermalSolo: true };
  if (mode === "thermal_pip") return { mainView: "thermal", thermalSolo: false };
  return { mainView: "visible", thermalSolo: false };
}

type Store = {
  url: string;
  setUrl: (url: string) => void;
  layout: GcsLayout;
  setLayout: (patch: Partial<GcsLayout>) => void;
  connected: boolean;
  setConnected: (v: boolean) => void;
  telemetry: Telemetry;
  setTelemetry: (t: Telemetry) => void;
  visibleUrl: string | null;
  thermalUrl: string | null;
  setFrame: (stream: 0 | 1, blobUrl: string) => void;
  mainView: "visible" | "thermal";
  setMainView: (v: "visible" | "thermal") => void;
  /** Khi main = thermal: true = chỉ ảnh nhiệt (ẩn PiP ảnh thường). */
  thermalSolo: boolean;
  setThermalSolo: (v: boolean) => void;
  pointerMode: PointerMode;
  setPointerMode: (m: PointerMode) => void;
  settingsOpen: boolean;
  setSettingsOpen: (v: boolean) => void;
  jetsonConfig: Record<string, unknown> | null;
  setJetsonConfig: (c: Record<string, unknown> | null) => void;
  configStatus: string | null;
  setConfigStatus: (s: string | null) => void;
  reconnectNonce: number;
  reconnect: () => void;
  keys: Set<string>;
};

const initialLayout = loadLayout();
const initialView = viewModeToState(initialLayout.defaultViewMode);

export const useStore = create<Store>((set, get) => ({
  url: localStorage.getItem(URL_KEY) || "ws://127.0.0.2:8765/ws",
  setUrl: (url) => {
    localStorage.setItem(URL_KEY, url);
    set({ url });
  },
  layout: initialLayout,
  setLayout: (patch) => {
    const layout = migrateLayout({ ...get().layout, ...patch } as unknown as Record<string, unknown>);
    localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout));
    set({ layout });
  },
  connected: false,
  setConnected: (connected) => set({ connected }),
  telemetry: emptyTelemetry(),
  setTelemetry: (telemetry) => set({ telemetry }),
  visibleUrl: null,
  thermalUrl: null,
  setFrame: (stream, blobUrl) => {
    const prev = stream === 0 ? get().visibleUrl : get().thermalUrl;
    if (prev) URL.revokeObjectURL(prev);
    if (stream === 0) set({ visibleUrl: blobUrl });
    else set({ thermalUrl: blobUrl });
  },
  mainView: initialView.mainView,
  setMainView: (mainView) => set({ mainView }),
  thermalSolo: initialView.thermalSolo,
  setThermalSolo: (thermalSolo) => set({ thermalSolo }),
  pointerMode: "track",
  setPointerMode: (pointerMode) => set({ pointerMode }),
  settingsOpen: false,
  setSettingsOpen: (settingsOpen) => set({ settingsOpen }),
  jetsonConfig: null,
  setJetsonConfig: (jetsonConfig) => set({ jetsonConfig }),
  configStatus: null,
  setConfigStatus: (configStatus) => set({ configStatus }),
  reconnectNonce: 0,
  reconnect: () => set({ reconnectNonce: get().reconnectNonce + 1 }),
  keys: new Set(),
}));

export function applyViewMode(mode: DefaultViewMode) {
  const { mainView, thermalSolo } = viewModeToState(mode);
  useStore.setState({ mainView, thermalSolo });
}
