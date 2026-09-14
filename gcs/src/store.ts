import { create } from "zustand";
import { emptyTelemetry, type Telemetry } from "./types";

export type PointerMode = "track" | "roi";

type Store = {
  url: string;
  setUrl: (url: string) => void;
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
  keys: Set<string>;
};

const KEY = "eo.ws.url";

export const useStore = create<Store>((set, get) => ({
  url: localStorage.getItem(KEY) || "ws://127.0.0.1:8765/ws",
  setUrl: (url) => {
    localStorage.setItem(KEY, url);
    set({ url });
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
  mainView: "visible",
  setMainView: (mainView) => set({ mainView }),
  pointerMode: "track",
  setPointerMode: (pointerMode) => set({ pointerMode }),
  keys: new Set(),
}));
