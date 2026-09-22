export type Detection = {
  id: number;
  cls: string;
  conf: number;
  x: number;
  y: number;
  w: number;
  h: number;
};

export type GpsFix = {
  lat: number;
  lon: number;
  alt: number;
  fix: boolean;
};

export type TargetGeo = {
  lat: number;
  lon: number;
  alt: number;
  valid: boolean;
};

export type Telemetry = {
  type: "telemetry";
  sim: boolean;
  pan: number;
  tilt: number;
  zoom: number;
  fov_h: number;
  fov_v: number;
  laser_m: number | null;
  laser_valid: boolean;
  gps: GpsFix;
  heading: number;
  camera: {
    source: "visible" | "thermal";
    autofocus: boolean;
    brightness: number;
    contrast: number;
    quality: string;
    fps: number;
  };
  detect_on: boolean;
  track_on: boolean;
  track_id: number | null;
  ai_ok?: boolean;
  ai_model?: string | null;
  roi: number[] | null;
  recording: boolean;
  detections: Detection[];
  target_geo: TargetGeo;
  last_photo: string | null;
};

export const emptyTelemetry = (): Telemetry => ({
  type: "telemetry",
  sim: false,
  pan: 0,
  tilt: 0,
  zoom: 1,
  fov_h: 60,
  fov_v: 34,
  laser_m: null,
  laser_valid: false,
  gps: { lat: 21.0285, lon: 105.8542, alt: 0, fix: false },
  heading: 0,
  camera: {
    source: "visible",
    autofocus: true,
    brightness: 50,
    contrast: 50,
    quality: "720p",
    fps: 15,
  },
  detect_on: true,
  track_on: false,
  track_id: null,
  ai_ok: false,
  ai_model: null,
  roi: null,
  recording: false,
  detections: [],
  target_geo: { lat: 0, lon: 0, alt: 0, valid: false },
  last_photo: null,
});
