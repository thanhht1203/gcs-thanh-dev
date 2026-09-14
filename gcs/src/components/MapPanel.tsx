import { MapContainer, TileLayer, Marker, Popup, Polyline, CircleMarker, useMap } from "react-leaflet";
import L from "leaflet";
import { useEffect } from "react";
import { useStore } from "../store";

import "leaflet/dist/leaflet.css";

const ownIcon = L.divIcon({
  className: "own-icon",
  html: `<div class="own-mark"></div>`,
  iconSize: [18, 18],
  iconAnchor: [9, 9],
});

const tgtIcon = L.divIcon({
  className: "tgt-icon",
  html: `<div class="tgt-mark"></div>`,
  iconSize: [16, 16],
  iconAnchor: [8, 8],
});

function Recenter({ lat, lon }: { lat: number; lon: number }) {
  const map = useMap();
  useEffect(() => {
    map.setView([lat, lon]);
  }, [lat, lon, map]);
  return null;
}

export function MapPanel() {
  const gps = useStore((s) => s.telemetry.gps);
  const tgt = useStore((s) => s.telemetry.target_geo);
  const heading = useStore((s) => s.telemetry.heading);
  const lat = gps.lat || 21.0285;
  const lon = gps.lon || 105.8542;

  return (
    <div className="map-wrap">
      <div className="map-label">BẢN ĐỒ · TỌA ĐỘ MỤC TIÊU</div>
      <MapContainer center={[lat, lon]} zoom={14} className="map" zoomControl={false}>
        <TileLayer
          attribution="&copy; OSM"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <Recenter lat={lat} lon={lon} />
        <Marker position={[lat, lon]} icon={ownIcon}>
          <Popup>Thiết bị</Popup>
        </Marker>
        <CircleMarker
          center={[lat, lon]}
          radius={18}
          pathOptions={{ color: "#3ddc97", weight: 1, fillOpacity: 0.05 }}
        />
        {tgt.valid && (
          <>
            <Marker position={[tgt.lat, tgt.lon]} icon={tgtIcon}>
              <Popup>
                Mục tiêu
                <br />
                {tgt.lat.toFixed(6)}, {tgt.lon.toFixed(6)}
              </Popup>
            </Marker>
            <Polyline
              positions={[
                [lat, lon],
                [tgt.lat, tgt.lon],
              ]}
              pathOptions={{ color: "#ffb000", weight: 2, dashArray: "4 4" }}
            />
          </>
        )}
      </MapContainer>
      <div className="map-readout">
        <div>
          TB: {gps.fix ? `${lat.toFixed(6)}, ${lon.toFixed(6)}` : "GPS mất tín hiệu"} · HDG {heading.toFixed(0)}°
        </div>
        <div>
          MT:{" "}
          {tgt.valid
            ? `${tgt.lat.toFixed(6)}, ${tgt.lon.toFixed(6)}  (${tgt.alt.toFixed(0)} m)`
            : "chưa xác định (cần GPS + góc / laser)"}
        </div>
      </div>
    </div>
  );
}
