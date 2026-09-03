"""One-shot map builder for the MilitaryTab ADIZ schematic.

Pulls Natural Earth 50m admin0 polygons for Taiwan + China, clips to a
Taiwan-Strait bounding box, simplifies with Douglas-Peucker, projects to
the component's SVG viewBox (0..320, 0..260), and emits a JS module of
path strings the React component imports.

Re-run only if you want to retune resolution, bbox, or viewBox.

    python scripts/build_taiwan_strait_map.py
"""
from __future__ import annotations
import json
import math
import urllib.request
from pathlib import Path

NE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_10m_admin_0_countries.geojson"
)
# Matsu (and various other very small islands) is too small to appear in the
# admin0 layer even at 10m — it lives only in minor_islands.
NE_MINOR_ISLANDS_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_10m_minor_islands.geojson"
)

# Taiwan Strait region. Captures Fujian + a bit of Guangdong + Taiwan + nearby
# islands (Penghu, Matsu, Kinmen, Lanyu, Green Island). The MND ADIZ sectors
# fan out around Taiwan proper, so anything outside this rectangle is
# irrelevant. Pratas/Itu Aba sit far enough south-west to be off-screen.
BBOX = (117.0, 21.0, 123.5, 26.5)
SVG_W = 320
SVG_H = 260

# Coast-near margin (degrees). The China mainland polygon is huge — we walk
# the ring and only keep contiguous runs of points that fall within
# BBOX expanded by this margin. The visual result is the coastline entering
# and leaving the canvas at the edges (rather than a closed shape).
COAST_MARGIN = 0.6

# Douglas-Peucker tolerance in degrees. 10m is much denser than 50m, so we
# can afford a tighter tolerance and still get manageable path strings.
EPSILON_TW = 0.005   # ~550 m — preserves small islands like Lanyu / Green Island
EPSILON_CN = 0.020   # ~2.2 km — mainland coast doesn't need cm precision

# ROC-controlled outlying islands. Natural Earth handles these inconsistently:
#   * Kinmen is filed under China (de jure)
#   * Matsu / Wuqiu are missing from admin0 and live only in minor_islands
# Any polygon (from either source) whose centroid lands inside one of these
# bboxes is rendered as ROC territory.
ROC_OUTLYING = [
    # (label, lon_min, lat_min, lon_max, lat_max)
    ("Matsu-NB",  119.85, 26.05, 120.10, 26.30),  # Nangan + Beigan group
    ("Matsu-Ju",  119.85, 25.93, 120.00, 26.02),  # Juguang group
    ("Matsu-DY",  120.40, 26.30, 120.55, 26.45),  # Dongyin / Xiyin
    # Kinmen west edge sits at 118.20 to keep Xiamen (PRC, centroid
    # ~118.12) out of the rectangle. North edge at 24.55 to exclude
    # Dadeng / Xiaodeng (PRC-controlled since 1958, claimed by ROC).
    ("Kinmen",    118.20, 24.30, 118.55, 24.55),
    ("Wuqiu",     119.30, 24.85, 119.50, 24.95),
]
# A polygon is "small" if its lon/lat bounding box span is <= this — used to
# avoid mis-classifying a chunk of mainland China that happens to brush an
# ROC bbox.
ROC_MAX_SPAN_DEG = 0.6

# Equirectangular projection with cos-lat correction for the bbox centre.
LAT0 = (BBOX[1] + BBOX[3]) / 2
COSL = math.cos(math.radians(LAT0))

# Aspect-correct horizontal scale: pixels per degree-lon should match
# pixels per degree-lat × cos(LAT0). Compute base scale from height.
PX_PER_DEG_LAT = SVG_H / (BBOX[3] - BBOX[1])
PX_PER_DEG_LON = PX_PER_DEG_LAT * COSL
TOTAL_LON_PX = PX_PER_DEG_LON * (BBOX[2] - BBOX[0])
X_OFFSET = (SVG_W - TOTAL_LON_PX) / 2  # centre the strait horizontally


def project(lon: float, lat: float) -> tuple[float, float]:
    x = X_OFFSET + (lon - BBOX[0]) * PX_PER_DEG_LON
    y = (BBOX[3] - lat) * PX_PER_DEG_LAT
    return x, y


def perp_dist(p, a, b):
    x0, y0 = p
    x1, y1 = a
    x2, y2 = b
    if (x1, y1) == (x2, y2):
        return math.hypot(x0 - x1, y0 - y1)
    return abs((y2 - y1) * x0 - (x2 - x1) * y0 + x2 * y1 - y2 * x1) / math.hypot(x2 - x1, y2 - y1)


def dp(points, eps):
    if len(points) < 3:
        return list(points)
    dmax, idx = 0.0, 0
    end = len(points) - 1
    for i in range(1, end):
        d = perp_dist(points[i], points[0], points[end])
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        a = dp(points[: idx + 1], eps)
        b = dp(points[idx:], eps)
        return a[:-1] + b
    return [points[0], points[end]]


def in_bbox(lon, lat, margin=0.0):
    return (BBOX[0] - margin <= lon <= BBOX[2] + margin
            and BBOX[1] - margin <= lat <= BBOX[3] + margin)


def closed_polygon_path(ring, eps):
    """Closed shape — Taiwan sits entirely inside the bbox."""
    pts = dp(list(ring), eps)
    proj = [project(lon, lat) for lon, lat in pts]
    if not proj:
        return ""
    return ("M " + f"{proj[0][0]:.2f} {proj[0][1]:.2f} "
            + " ".join(f"L {x:.2f} {y:.2f}" for x, y in proj[1:])
            + " Z")


def coastline_segments(ring, eps, margin=COAST_MARGIN):
    """Walk a ring and emit contiguous open segments inside bbox+margin."""
    segments = []
    current = []
    for lon, lat in ring:
        if in_bbox(lon, lat, margin):
            current.append((lon, lat))
        else:
            if len(current) >= 4:
                segments.append(current)
            current = []
    if len(current) >= 4:
        segments.append(current)

    paths = []
    for seg in segments:
        simp = dp(seg, eps)
        proj = [project(lon, lat) for lon, lat in simp]
        if len(proj) < 2:
            continue
        d = ("M " + f"{proj[0][0]:.2f} {proj[0][1]:.2f} "
             + " ".join(f"L {x:.2f} {y:.2f}" for x, y in proj[1:]))
        paths.append(d)
    return paths


def ring_centroid(ring):
    return (sum(p[0] for p in ring) / len(ring),
            sum(p[1] for p in ring) / len(ring))


def ring_span(ring):
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return max(xs) - min(xs), max(ys) - min(ys)


def in_roc_outlying(cx, cy, dx, dy):
    """True if a polygon centroid+span looks like an ROC outlying island
    sitting inside one of our hand-defined bboxes."""
    if dx > ROC_MAX_SPAN_DEG or dy > ROC_MAX_SPAN_DEG:
        return False
    for _, x0, y0, x1, y1 in ROC_OUTLYING:
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            return True
    return False


def main():
    print(f"Fetching {NE_URL}")
    raw = urllib.request.urlopen(NE_URL).read()
    data = json.loads(raw)

    taiwan_paths: list[str] = []
    china_paths: list[str] = []
    reclassified: list[str] = []

    for feature in data["features"]:
        props = feature["properties"]
        admin = props.get("ADMIN") or props.get("NAME")
        geom = feature["geometry"]
        polys = (
            [geom["coordinates"]] if geom["type"] == "Polygon"
            else geom["coordinates"] if geom["type"] == "MultiPolygon"
            else []
        )

        if admin == "Taiwan":
            for poly in polys:
                outer = poly[0]
                cx, cy = ring_centroid(outer)
                if not in_bbox(cx, cy, margin=0.5):
                    continue
                path = closed_polygon_path(outer, EPSILON_TW)
                if path:
                    taiwan_paths.append(path)
        elif admin == "China":
            for poly in polys:
                outer = poly[0]
                cx, cy = ring_centroid(outer)
                dx, dy = ring_span(outer)
                # ROC-controlled outlying islands that Natural Earth files
                # under China (Kinmen primarily) — render as Taiwan.
                if in_roc_outlying(cx, cy, dx, dy):
                    path = closed_polygon_path(outer, EPSILON_TW)
                    if path:
                        taiwan_paths.append(path)
                        reclassified.append(f"admin0 ({cx:.2f},{cy:.2f}) span={dx:.2f}x{dy:.2f}")
                    continue
                # Otherwise: the mainland polygon (or a small mainland-Fujian
                # island) — extract bbox-adjacent coastline runs.
                china_paths.extend(coastline_segments(outer, EPSILON_CN))

    # Pass 2: minor_islands. NE 10m admin0 omits very small islands like
    # Matsu's island groups; minor_islands carries them. We pull anything in
    # our bbox whose centroid lands inside one of the ROC bboxes.
    print(f"Fetching {NE_MINOR_ISLANDS_URL}")
    raw_mi = urllib.request.urlopen(NE_MINOR_ISLANDS_URL).read()
    mi_data = json.loads(raw_mi)
    for feature in mi_data["features"]:
        geom = feature["geometry"]
        polys = (
            [geom["coordinates"]] if geom["type"] == "Polygon"
            else geom["coordinates"] if geom["type"] == "MultiPolygon"
            else []
        )
        for poly in polys:
            outer = poly[0]
            cx, cy = ring_centroid(outer)
            dx, dy = ring_span(outer)
            if not in_bbox(cx, cy):
                continue
            if not in_roc_outlying(cx, cy, dx, dy):
                continue
            path = closed_polygon_path(outer, EPSILON_TW)
            if path:
                taiwan_paths.append(path)
                reclassified.append(f"minor ({cx:.2f},{cy:.2f})")

    # Taiwan Strait Median Line (the "Davis Line", named for USAF Gen.
    # Benjamin O. Davis Jr.). MND publishes it running from roughly
    # 27°N 122°E in the north to 23°17'N 117°51'E in the south. We clip
    # the northern endpoint to the bbox top so the line enters from the
    # top edge rather than disappearing off-canvas.
    MEDIAN_NORTH = (122.0, 27.0)
    MEDIAN_SOUTH = (117.85, 23.283)
    if MEDIAN_NORTH[1] > BBOX[3]:
        slope_lon = (MEDIAN_NORTH[0] - MEDIAN_SOUTH[0]) / (MEDIAN_NORTH[1] - MEDIAN_SOUTH[1])
        clipped_lon = MEDIAN_NORTH[0] - slope_lon * (MEDIAN_NORTH[1] - BBOX[3])
        median_north = (clipped_lon, BBOX[3])
    else:
        median_north = MEDIAN_NORTH
    n_px = project(*median_north)
    s_px = project(*MEDIAN_SOUTH)

    out_js = (
        "// Auto-generated by scripts/build_taiwan_strait_map.py. Do not hand-edit.\n"
        f"// viewBox: 0 0 {SVG_W} {SVG_H}; bbox(lon/lat) = {BBOX}\n"
        "//\n"
        "// TAIWAN_PATHS is a list of closed polygon strings (main island +\n"
        "// outlying islands: Penghu, Kinmen, Matsu, Lanyu, Green Island).\n"
        "// PRC_COAST_PATHS is open polylines of the nearby mainland coast —\n"
        "// render as `stroke` with no fill.\n"
        "// MEDIAN_LINE is the Taiwan Strait Median Line (Davis Line) endpoints\n"
        "// already projected into the SVG viewBox.\n\n"
        f"export const TAIWAN_PATHS = {json.dumps(taiwan_paths)};\n"
        f"export const PRC_COAST_PATHS = {json.dumps(china_paths)};\n"
        f"export const MEDIAN_LINE = {{ "
        f"x1: {n_px[0]:.2f}, y1: {n_px[1]:.2f}, "
        f"x2: {s_px[0]:.2f}, y2: {s_px[1]:.2f} }};\n"
    )

    output = Path("frontend/src/components/taiwanStraitMap.js")
    output.write_text(out_js, encoding="utf-8")
    print(f"Wrote {output}")
    print(f"  Taiwan polygons: {len(taiwan_paths)}  (chars: {sum(len(p) for p in taiwan_paths)})")
    print(f"  PRC coast segments: {len(china_paths)}  (chars: {sum(len(p) for p in china_paths)})")
    if reclassified:
        print(f"  Re-classified as ROC: {', '.join(reclassified)}")


if __name__ == "__main__":
    main()
