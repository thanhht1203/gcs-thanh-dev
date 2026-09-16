import { useEffect, useRef } from "react";
import { useStore } from "./store";
import type { Telemetry } from "./types";

type Pending = {
  resolve: (v: unknown) => void;
  reject: (e: Error) => void;
  timer: number;
};

const pendingConfig = new Map<string, Pending>();

export function send(obj: unknown) {
  const ws = wsRef.current;
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(obj));
    return true;
  }
  return false;
}

/** Gửi lệnh config và chờ phản hồi (requestId). */
export function requestConfig(action: "get" | "set", config?: Record<string, unknown>, persist = true) {
  const requestId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  return new Promise<Record<string, unknown>>((resolve, reject) => {
    if (!send({ type: "config", action, config, persist, requestId })) {
      reject(new Error("Chưa kết nối Jetson"));
      return;
    }
    const timer = window.setTimeout(() => {
      pendingConfig.delete(requestId);
      reject(new Error("Hết thời gian chờ phản hồi config"));
    }, 15000);
    pendingConfig.set(requestId, {
      resolve: (v) => resolve(v as Record<string, unknown>),
      reject,
      timer,
    });
  });
}

function settleConfig(msg: Record<string, unknown>) {
  const requestId = typeof msg.requestId === "string" ? msg.requestId : null;
  if (requestId && pendingConfig.has(requestId)) {
    const p = pendingConfig.get(requestId)!;
    pendingConfig.delete(requestId);
    window.clearTimeout(p.timer);
    if (msg.config && typeof msg.config === "object") {
      useStore.getState().setJetsonConfig(msg.config as Record<string, unknown>);
    }
    if (msg.ok === false) p.reject(new Error(String(msg.error || "Config lỗi")));
    else p.resolve(msg);
    return;
  }
  if (msg.config && typeof msg.config === "object") {
    useStore.getState().setJetsonConfig(msg.config as Record<string, unknown>);
  }
}

const wsRef: { current: WebSocket | null } = { current: null };

export function useJetsonSocket() {
  const url = useStore((s) => s.url);
  const reconnectNonce = useStore((s) => s.reconnectNonce);
  const setConnected = useStore((s) => s.setConnected);
  const setTelemetry = useStore((s) => s.setTelemetry);
  const setFrame = useStore((s) => s.setFrame);
  const retry = useRef<number>(0);

  useEffect(() => {
    let closed = false;
    let sock: WebSocket | null = null;
    let timer: number | undefined;

    const connect = () => {
      if (closed) return;
      try {
        sock = new WebSocket(url);
      } catch {
        timer = window.setTimeout(connect, 1500);
        return;
      }
      wsRef.current = sock;
      sock.binaryType = "arraybuffer";
      sock.onopen = () => {
        if (wsRef.current !== sock) return;
        retry.current = 0;
        setConnected(true);
      };
      sock.onclose = () => {
        // Chỉ cập nhật state nếu đây vẫn là socket hiện tại (tránh HMR/reconnect race)
        if (wsRef.current === sock) {
          wsRef.current = null;
          setConnected(false);
        }
        if (!closed) {
          retry.current += 1;
          timer = window.setTimeout(connect, Math.min(4000, 600 * retry.current));
        }
      };
      sock.onerror = () => {
        try {
          sock?.close();
        } catch {
          /* ignore */
        }
      };
      sock.onmessage = (ev) => {
        if (wsRef.current !== sock) return;
        if (typeof ev.data === "string") {
          try {
            const msg = JSON.parse(ev.data);
            if (msg.type === "telemetry") setTelemetry(msg as Telemetry);
            else if (msg.type === "config") settleConfig(msg);
          } catch {
            /* ignore */
          }
          return;
        }
        const buf = ev.data as ArrayBuffer;
        if (buf.byteLength < 2) return;
        const view = new Uint8Array(buf);
        const stream = view[0] === 1 ? 1 : 0;
        const blob = new Blob([view.slice(1)], { type: "image/jpeg" });
        setFrame(stream, URL.createObjectURL(blob));
      };
    };

    connect();
    return () => {
      closed = true;
      if (timer) window.clearTimeout(timer);
      const s = sock;
      if (s) {
        s.onopen = null;
        s.onclose = null;
        s.onerror = null;
        s.onmessage = null;
        try {
          s.close();
        } catch {
          /* ignore */
        }
      }
      if (wsRef.current === s) {
        wsRef.current = null;
        setConnected(false);
      }
    };
  }, [url, reconnectNonce, setConnected, setTelemetry, setFrame]);
}
