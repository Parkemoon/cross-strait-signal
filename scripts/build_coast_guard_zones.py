"""Build the Coast Guard tracker zone polygons.

Writes `data/coast_guard_zones.geojson` (server-side: each zone polygon is
POSTed to Global Fishing Watch's 4Wings report endpoint as the query region —
see scraper/scrapers/gfw_coast_guard.py) and copies it to
`frontend/public/geo/` for the map layer.

Zones (Ed's v1 set, 2026-08-25 — "all six"):

  kinmen_prohibited / kinmen_restricted      金門禁止水域 / 限制水域
  matsu_prohibited  / matsu_restricted       馬祖禁止水域 / 限制水域
  median_line_east                           12 nm band on the Taiwan side of the median line
  contiguous_{n,e,s,w}                       Taiwan 24 nm contiguous zone, four sectors
  pratas_24nm                                Pratas (東沙) 24 nm
  east_coast_box                             analytical box east of Taiwan (the "drift east" story)

Geometry sources: Natural Earth 1:10m admin0 + minor_islands (the same two
files scripts/build_taiwan_strait_map.py uses; Kinmen is filed under China
in admin0, Matsu/Wuqiu only exist in minor_islands — the ROC_OUTLYING bboxes
below are copied from that script for the same reason).

Legal geometry (see COAST_GUARD_TRACKER_SCOPE.md §4):
  * KINMEN — built from the OFFICIAL boundary: the 21 WGS-84 control points
    of the county's outer line (Kinmen County 公告 府建漁字第1090014433號,
    2020-02-21, map "金門地區限制、禁止水域界線圖"), which is the MND
    restricted-waters line (國防部 93.6.7 猛獅字第0930001493號) pushed out by
    300 m (1,000 m on the east/south segments). We shrink it back, and indent
    the prohibited line ~2.5 km on the east/south (the inner vertex labels on
    the gazette map are illegible — ⚑ approximation).
  * MATSU — no official vertex list found: uniform 4 km / 6 km bands from
    the NE 10m coastlines, clipped to the points nearer Matsu than the PRC
    coast (the legal zones stop halfway to the mainland).
  * GFW presence cells are 0.01° (~1 km), so sub-kilometre fidelity buys
    nothing — but numbers are "hull-days inside OUR polygon", and the UI must
    say so. Validation 2026-08-25: March 2024 (AMTI's peak month) → 14 CCG
    hull-days in the Kinmen zones, consistent with the CGA's tally of ~4
    four-ship incursions a month.

Re-run only to retune buffers / sectors; output is committed.
"""
from __future__ import annotations

import json
import math
import sys
import urllib.request
from pathlib import Path

from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box, mapping, shape
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "coast_guard_zones.geojson"
OUT_FRONTEND = ROOT / "frontend" / "public" / "geo" / "coast_guard_zones.geojson"

NE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_10m_admin_0_countries.geojson"
)
NE_MINOR_ISLANDS_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_10m_minor_islands.geojson"
)

# Copied from scripts/build_taiwan_strait_map.py (keep in lockstep).
ROC_OUTLYING = {
    "matsu": [(119.85, 26.05, 120.10, 26.30), (119.85, 25.93, 120.00, 26.02), (120.40, 26.30, 120.55, 26.45)],
    "kinmen": [(118.20, 24.30, 118.55, 24.55)],
    # Dadan / Erdan sit SW of Lieyu at ~118.23E 24.39N — inside the Kinmen bbox.
}
KM = 1000.0
NM = 1852.0

# Kinmen/Matsu band widths (km from the island coastline, clipped at the
# midline to the PRC coast). See the legal-geometry caveat above; tune here.
INNER_KM = 4.0    # prohibited
OUTER_KM = 6.0    # restricted (outer edge)

# Median line: the conventional 1955 "Davis line" waypoints (N→S). MND
# publishes no polygon; these are the coordinates used across the
# literature and in the Positions page's median-line concept entry.
MEDIAN_LINE = [(121.3833, 26.5), (119.9833, 24.8333), (117.85, 23.2833)]
MEDIAN_BAND_M = 12 * NM

TAIWAN_CENTROID = (121.0, 23.7)
PRATAS = (116.72, 20.70)
EAST_BOX = (121.8, 21.8, 124.5, 25.6)   # lon_min, lat_min, lon_max, lat_max
CONTIGUOUS_M = 24 * NM

# Local equirectangular projection — good to ~1% at these latitudes, plenty
# for kilometre-scale buffers.
LAT0 = 24.5
_KX = 111_320.0 * math.cos(math.radians(LAT0))
_KY = 110_574.0


def _fwd(x, y, z=None):
    return (x * _KX, y * _KY)


def _inv(x, y, z=None):
    return (x / _KX, y / _KY)


def to_m(g):
    return transform(_fwd, g)


def to_deg(g):
    return transform(_inv, g)


def _load(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.load(r)


def _rings(feature_collection, admin_names=None):
    """Yield (polygon, centroid) for every ring of every matching feature."""
    for f in feature_collection["features"]:
        props = f.get("properties", {})
        if admin_names and props.get("ADMIN") not in admin_names and props.get("NAME") not in admin_names:
            continue
        g = shape(f["geometry"])
        polys = list(g.geoms) if isinstance(g, MultiPolygon) else [g]
        for p in polys:
            yield p


def _in_bboxes(p, bboxes):
    c = p.centroid
    return any(x0 <= c.x <= x1 and y0 <= c.y <= y1 for (x0, y0, x1, y1) in bboxes)


def _dms(d, m, s):
    return d + m / 60 + s / 3600


# Kinmen: the OUTER boundary line published by Kinmen County (公告 府建漁字第
# 1090014433號, 2020-02-21, map "金門地區限制、禁止水域界線圖 (WGS-84)"),
# transcribed from the gazette's coordinate table. That line is the MND
# restricted-waters boundary (國防部 93.6.7 猛獅字第0930001493號) pushed OUT by
# 300 m, or by 1,000 m along the east/south segments between control points
# 1 (due east) and 9 (due south). Points run clockwise from the NE tip.
KINMEN_OUTER_DMS = [
    (1, (118, 31, 22), (24, 29, 43)), (2, (118, 31, 46), (24, 28, 13)), (3, (118, 32, 46), (24, 25, 37)),
    (4, (118, 30, 34), (24, 21, 49)), (5, (118, 27, 52), (24, 19, 20)), (6, (118, 23, 12), (24, 20, 29)),
    (7, (118, 19, 11), (24, 17, 39)), (8, (118, 16, 34), (24, 18, 24)), (9, (118, 13, 30), (24, 18, 44)),
    (10, (118, 9, 19), (24, 21, 37)), (11, (118, 7, 54), (24, 22, 56)), (12, (118, 8, 49), (24, 24, 36)),
    (13, (118, 11, 49), (24, 26, 15)), (13.5, (118, 12, 22), (24, 27, 8)), (14, (118, 13, 54), (24, 28, 41)),
    (15, (118, 16, 31), (24, 30, 19)), (16, (118, 19, 51), (24, 30, 32)), (17, (118, 23, 4), (24, 31, 55)),
    (18, (118, 24, 19), (24, 32, 34)), (19, (118, 26, 58), (24, 31, 43)), (20, (118, 27, 41), (24, 31, 6)),
]
KINMEN_OUTER = [(_dms(*e), _dms(*n)) for _, e, n in KINMEN_OUTER_DMS]
KINMEN_EAST_SOUTH = [(_dms(*e), _dms(*n)) for i, e, n in KINMEN_OUTER_DMS if i <= 9]
# The prohibited line is drawn ~2–3 km inside the restricted line on the
# east/south side only (identical on the west/north, where the restricted
# line IS the de-facto border with Xiamen). The gazette map's inner-vertex
# labels are illegible at print resolution, so the indent is approximated —
# ⚑ replace with the MND 公告 vertex list if it surfaces.
KINMEN_PROHIBITED_INDENT_M = 2500.0


def kinmen_official_zones(islands):
    land = to_m(unary_union(islands))
    outer = to_m(Polygon(KINMEN_OUTER)).buffer(0)
    east_south = to_m(LineString(KINMEN_EAST_SOUTH))
    # undo the county's outward buffer: 300 m everywhere, 1,000 m along 1→9
    restricted_outer = outer.buffer(-300).difference(east_south.buffer(700))
    prohibited = restricted_outer.difference(east_south.buffer(700 + KINMEN_PROHIBITED_INDENT_M))
    restricted_outer = restricted_outer.difference(land).difference(prc_m_global)
    prohibited = prohibited.difference(land).difference(prc_m_global)
    restricted = restricted_outer.difference(prohibited)
    return [
        ("kinmen_prohibited", "金門禁止水域", "kinmen", "prohibited", to_deg(prohibited)),
        ("kinmen_restricted", "金門限制水域", "kinmen", "restricted", to_deg(restricted)),
    ]


prc_m_global = None


def build():
    global prc_m_global
    print("fetching Natural Earth 10m …", file=sys.stderr)
    admin0 = _load(NE_URL)
    minor = _load(NE_MINOR_ISLANDS_URL)

    china_rings = list(_rings(admin0, {"China", "People's Republic of China"}))
    taiwan_rings = list(_rings(admin0, {"Taiwan"}))
    minor_rings = list(_rings(minor))

    # Kinmen main island is filed under TAIWAN in the current NE 10m release
    # (Lieyu under China) — search every ring set, or the zone silently
    # becomes a Lieyu-only buffer (2026-08-25 bug).
    kinmen = [p for p in china_rings + taiwan_rings + minor_rings if _in_bboxes(p, ROC_OUTLYING["kinmen"])]
    matsu = [p for p in minor_rings + china_rings + taiwan_rings if _in_bboxes(p, ROC_OUTLYING["matsu"])]
    prc_land = unary_union([p for p in china_rings if not _in_bboxes(p, ROC_OUTLYING["kinmen"] + ROC_OUTLYING["matsu"])])
    taiwan_main = max(taiwan_rings, key=lambda p: p.area)
    taiwan_all = unary_union(taiwan_rings + matsu + kinmen)
    print(f"  kinmen rings={len(kinmen)} matsu rings={len(matsu)} taiwan rings={len(taiwan_rings)}", file=sys.stderr)
    assert kinmen and matsu, "Natural Earth fetch returned no Kinmen/Matsu rings — check bboxes"

    prc_m = to_m(prc_land)
    prc_m_global = prc_m

    def nearer_than_prc(land, dist_m, step_m=250.0):
        """Points within dist_m of `land` that are CLOSER to `land` than to PRC
        land — the 'halfway to the mainland' clip. {p : d_land(p) < d_prc(p)}
        equals the union over r of land.buffer(r) \\ prc.buffer(r), so a fine
        ladder of r approximates it. (The earlier buffer-subtraction version
        wiped out the whole Kinmen–Xiamen channel — 2026-08-25 bug.)"""
        parts = []
        r = step_m
        while r <= dist_m + 1e-6:
            parts.append(land.buffer(r).difference(prc_m.buffer(r)))
            r += step_m
        return unary_union(parts).difference(prc_m).difference(land)

    def island_zones(islands, prefix, label_zh, inner_km=INNER_KM, outer_km=OUTER_KM):
        land = to_m(unary_union(islands))
        inner = nearer_than_prc(land, inner_km * KM)
        outer = nearer_than_prc(land, outer_km * KM)
        restricted = outer.difference(inner)
        return [
            (f"{prefix}_prohibited", f"{label_zh}禁止水域", prefix, "prohibited", to_deg(inner)),
            (f"{prefix}_restricted", f"{label_zh}限制水域", prefix, "restricted", to_deg(restricted)),
        ]

    zones = []
    zones += kinmen_official_zones(kinmen)
    zones += island_zones(matsu, "matsu", "馬祖")

    # Median line band: 12 nm on the Taiwan (east) side of the line.
    line_m = to_m(LineString(MEDIAN_LINE))
    # offset_curve(+d) is the LEFT side of the line direction; the line runs
    # NE→SW, whose left is south-east — i.e. the Taiwan side.
    east_edge = line_m.offset_curve(MEDIAN_BAND_M)
    band = Polygon(list(line_m.coords) + list(east_edge.coords)[::-1]).buffer(0)
    band = band.difference(to_m(taiwan_all))
    band_deg = to_deg(band)
    assert band_deg.centroid.x > 119.5, "median band ended up on the wrong side of the line"
    zones.append(("median_line_east", "海峽中線以東12浬帶", "median", "band", band_deg))

    # Taiwan 24 nm contiguous zone in four bearing sectors from the centroid.
    tw_m = to_m(taiwan_main)
    cz = tw_m.buffer(CONTIGUOUS_M).difference(to_m(taiwan_all)).difference(prc_m)
    cx, cy = _fwd(*TAIWAN_CENTROID)
    R = 600 * KM
    sectors = {"n": (315, 45), "e": (45, 135), "s": (135, 225), "w": (225, 315)}
    for key, (a0, a1) in sectors.items():
        pts = [(cx, cy)]
        a = a0
        while True:
            rad = math.radians(a)
            pts.append((cx + R * math.sin(rad), cy + R * math.cos(rad)))  # bearing: 0=N, 90=E
            if a % 360 == a1 % 360:
                break
            a += 5
        wedge = Polygon(pts)
        zones.append((f"contiguous_{key}", f"臺灣24浬鄰接區（{ {'n': '北', 'e': '東', 's': '南', 'w': '西'}[key] }）",
                      "contiguous", "sector", to_deg(cz.intersection(wedge))))

    pratas = to_deg(Point(_fwd(*PRATAS)).buffer(CONTIGUOUS_M))
    zones.append(("pratas_24nm", "東沙24浬", "pratas", "radius", pratas))

    east_box = box(*EAST_BOX).difference(taiwan_all)
    zones.append(("east_coast_box", "臺灣東部海域觀察框", "east", "box", east_box))

    features = []
    for zid, label_zh, group, kind, geom in zones:
        geom = geom.simplify(0.002, preserve_topology=True)
        features.append({
            "type": "Feature",
            "properties": {"id": zid, "label_zh": label_zh, "group": group, "kind": kind,
                           "label_en": LABEL_EN[zid], "area_km2": round(to_m(geom).area / 1e6)},
            "geometry": mapping(geom),
        })
        print(f"  {zid:20s} {round(to_m(geom).area / 1e6):>7} km²", file=sys.stderr)

    fc = {"type": "FeatureCollection",
          "_comment": "Generated by scripts/build_coast_guard_zones.py — do not hand-edit. "
                      "Kinmen/Matsu bands are a uniform 4 km / 6 km approximation of the MND 公告 distance bands, "
                      "clipped at the midline to the PRC coast; see COAST_GUARD_TRACKER_SCOPE.md §4.",
          "features": features}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fc, ensure_ascii=False))
    OUT_FRONTEND.parent.mkdir(parents=True, exist_ok=True)
    OUT_FRONTEND.write_text(json.dumps(fc, ensure_ascii=False))
    print(f"wrote {OUT} and {OUT_FRONTEND} ({len(features)} zones)", file=sys.stderr)


LABEL_EN = {
    "kinmen_prohibited": "Kinmen prohibited waters",
    "kinmen_restricted": "Kinmen restricted waters",
    "matsu_prohibited": "Matsu prohibited waters",
    "matsu_restricted": "Matsu restricted waters",
    "median_line_east": "Median line — Taiwan side (12 nm band)",
    "contiguous_n": "Taiwan 24 nm zone — north",
    "contiguous_e": "Taiwan 24 nm zone — east",
    "contiguous_s": "Taiwan 24 nm zone — south",
    "contiguous_w": "Taiwan 24 nm zone — west",
    "pratas_24nm": "Pratas 24 nm",
    "east_coast_box": "East-coast box",
}

if __name__ == "__main__":
    build()
