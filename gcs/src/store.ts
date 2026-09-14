import { create } from "zustand";
import { emptyTelemetry, type Telemetry } from "./types";

export type PointerMode = "track" | "roi";

export type GcsLayout = {
  sidebarWidth: number;
  bottomHeight: number;
  showPip: boolean;
  showMap: boolean;
  defaultMainView: "visible" | "thermal";
};

const URL_KEY = "eo.ws.url";
const LAYOUT_KEY = "eo.gcs.layout";

const defaultLayout = (): GcsLayout => ({
  sidebarWidth: 320,
  bottomHeight: 240,
  showPip: true,
  showMap: true,
  defaultMainView: "visible",
});

function loadLayout(): GcsLayout {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY);
    if (!raw) return defaultLayout();
    return { ...defaultLayout(), ...JSON.parse(raw) };
  } catch {
    return defaultLayout();
  }
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
  pointerMode: PointerMode;
  setPointerMode: (m: PointerMode) => void;
  settingsOpen: boolean;
  setSettingsOpen: (v: boolean) => void;
  jetsonConfig: Record<string, unknown> | null;
  setJetsonConfig: (c: Record<string, unknown> | null) => void;
  configStatus: string | null;
  setConfigStatus: (s: string | null) => void;
  keys: Set<string>;
};

const initialLayout = loadLayout();

export const useStore = create<Store>((set, get) => ({
  url: localStorage.getItem(URL_KEY) || "ws://127.0.0.1:8765/ws",
  setUrl: (url) => {
    localStorage.setItem(URL_KEY, url);
    set({ url });
  },
  layout: initialLayout,
  setLayout: (patch) => {
    const layout = { ...get().layout, ...patch };
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
  mainView: initialLayout.defaultMainView,
  setMainView: (mainView) => set({ mainView }),
  pointerMode: "track",
  setPointerMode: (pointerMode) => set({ pointerMode }),
  settingsOpen: false,
  setSettingsOpen: (settingsOpen) => set({ settingsOpen }),
  jetsonConfig: null,
  setJetsonConfig: (jetsonConfig) => set({ jetsonConfig }),
  configStatus: null,
  setConfigStatus: (configStatus) => set({ configStatus }),
  keys: new Set(),
}));
