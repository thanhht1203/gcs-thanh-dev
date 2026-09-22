import { useEffect, useRef } from "react";
import { useStore } from "../store";
import { send } from "../ws";

const held = new Set<string>();

function dirFromKeys() {
  let pan = 0;
  let tilt = 0;
  if (held.has("arrowleft") || held.has("a")) pan -= 1;
  if (held.has("arrowright") || held.has("d")) pan += 1;
  if (held.has("arrowup") || held.has("w")) tilt += 1;
  if (held.has("arrowdown") || held.has("s")) tilt -= 1;
  return { pan, tilt };
}

export function useHotkeys() {
  const repeating = useRef<number | null>(null);

  useEffect(() => {
    const onDown = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT") return;
      const k = e.key.toLowerCase();
      if (["arrowup", "arrowdown", "arrowleft", "arrowright", " "].includes(k) || k === "w" || k === "a" || k === "s" || k === "d") {
        e.preventDefault();
      }
      if (k === " " ) {
        send({ type: "record", action: "photo", save_to: "both" });
        return;
      }
      if (k === "h") send({ type: "ptz", action: "home" });
      if (k === "r") {
        const rec = useStore.getState().telemetry.recording;
        send({ type: "record", action: rec ? "stop" : "start" });
      }
      if (k === "+" || k === "=") send({ type: "zoom", action: "in" });
      if (k === "-" || k === "_") send({ type: "zoom", action: "out" });
      if (k === "t") send({ type: "track", action: "nearest" });
      if (k === "g") {
        const on = useStore.getState().telemetry.detect_on;
        send({ type: "detect", enabled: !on });
      }
      if (k === "escape") send({ type: "track", action: "stop" });
      if (k === "1") {
        useStore.getState().setMainView("visible");
        useStore.getState().setThermalSolo(false);
        useStore.getState().setLayout({ showPip: true });
        send({ type: "view", main: "visible" });
      }
      if (k === "2") {
        useStore.getState().setMainView("thermal");
        useStore.getState().setThermalSolo(false);
        send({ type: "view", main: "thermal" });
      }
      if (k === "3") {
        useStore.getState().setMainView("thermal");
        useStore.getState().setThermalSolo(true);
        send({ type: "view", main: "thermal" });
      }
      if (k === "0") {
        const { layout, mainView, setMainView, setLayout, setThermalSolo } = useStore.getState();
        if (mainView === "thermal" || layout.showPip) {
          setLayout({ showPip: false });
          setThermalSolo(false);
          if (mainView === "thermal") {
            setMainView("visible");
            send({ type: "view", main: "visible" });
          }
        } else {
          setLayout({ showPip: true });
        }
      }

      held.add(k);
      const { pan, tilt } = dirFromKeys();
      if (pan || tilt) send({ type: "ptz", action: "nudge", pan, tilt, speed: 1 });
    };

    const onUp = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      held.delete(k);
      const { pan, tilt } = dirFromKeys();
      if (!pan && !tilt) send({ type: "ptz", action: "stop" });
      else send({ type: "ptz", action: "nudge", pan, tilt, speed: 1 });
    };

    window.addEventListener("keydown", onDown);
    window.addEventListener("keyup", onUp);
    window.addEventListener("blur", () => {
      held.clear();
      send({ type: "ptz", action: "stop" });
    });
    return () => {
      window.removeEventListener("keydown", onDown);
      window.removeEventListener("keyup", onUp);
      if (repeating.current) window.clearInterval(repeating.current);
    };
  }, []);
}
