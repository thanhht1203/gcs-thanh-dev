import { useEffect, useRef } from "react";
import { useStore } from "./store";
import type { Telemetry } from "./types";

export function send(obj: unknown) {
  const ws = wsRef.current;
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(obj));
  }
}

const wsRef: { current: WebSocket | null } = { current: null };

export function useJetsonSocket() {
  const url = useStore((s) => s.url);
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
        retry.current = 0;
        setConnected(true);
      };
      sock.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        if (!closed) {
          retry.current += 1;
          timer = window.setTimeout(connect, Math.min(4000, 600 * retry.current));
        }
      };
      sock.onerror = () => sock?.close();
      sock.onmessage = (ev) => {
        if (typeof ev.data === "string") {
          try {
            const msg = JSON.parse(ev.data);
            if (msg.type === "telemetry") setTelemetry(msg as Telemetry);
            if (msg.type === "photo" && msg.path) {
              /* Jetson saved a still; GCS also keeps the on-screen frame via snapshot button */
            }
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
      sock?.close();
      wsRef.current = null;
      setConnected(false);
    };
  }, [url, setConnected, setTelemetry, setFrame]);
}
