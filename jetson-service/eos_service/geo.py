from __future__ import annotations

import math

from .state import GpsFix, TargetGeo


def wrap_deg(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


def quality_size(quality: str, fallback: tuple[int, int]) -> tuple[int, int]:
    q = (quality or "").lower()
    if q in ("1080p", "fullhd", "full-hd"):
        return 1920, 1080
    if q in ("720p", "hd"):
        return 1280, 720
    if q in ("480p", "sd"):
        return 854, 480
    return fallback


def compute_fov(fov_h_1x: float, zoom: float, aspect: float) -> tuple[float, float]:
    zoom = max(zoom, 0.1)
    fov_h = fov_h_1x / zoom
    # vertical from aspect (width/height)
    fov_v = math.degrees(2 * math.atan(math.tan(math.radians(fov_h) / 2) / max(aspect, 0.1)))
    return fov_h, fov_v


def target_geolocation(
    gps: GpsFix,
    heading_deg: float,
    pan_deg: float,
    tilt_deg: float,
    range_m: float | None,
    platform_height_m: float,
) -> TargetGeo:
    """Tính tọa độ mục tiêu từ GPS + heading + pan/tilt + laser (hoặc giao mặt đất)."""
    if not gps.fix:
        return TargetGeo()

    azimuth = math.radians(heading_deg + pan_deg)
    elev = math.radians(tilt_deg)

    if range_m is not None and range_m > 1.0:
        horiz = range_m * math.cos(elev)
        d_alt = range_m * math.sin(elev)
    else:
        # Giao tia nhìn với mặt đất (giả sử mục tiêu cùng độ cao địa hình)
        if tilt_deg >= -0.3:
            return TargetGeo()
        horiz = platform_height_m / max(math.tan(-elev), 1e-3)
        d_alt = -platform_height_m

    d_n = horiz * math.cos(azimuth)
    d_e = horiz * math.sin(azimuth)

    lat0 = math.radians(gps.lat)
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(lat0)
    lat = gps.lat + d_n / m_per_deg_lat
    lon = gps.lon + d_e / max(m_per_deg_lon, 1e-6)
    alt = gps.alt + d_alt
    return TargetGeo(lat=lat, lon=lon, alt=alt, valid=True)
