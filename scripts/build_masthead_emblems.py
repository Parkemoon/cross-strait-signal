"""Masthead emblems: the two sides of the strait as two filled silhouettes.

Ed's masthead idea (2026-09-02) — the nameplate sits in the strait, with the
mainland to the west and Taiwan to the east. Round 2 (one shared-scale map,
split on the Median Line) failed because a Fujian coast segment is not an
icon at any smoothing. This builder therefore produces two INDEPENDENT
emblems, each at its own scale, each filled:

  * MAINLAND — China's eastern seaboard from the Shandong peninsula down past
    the Yangtze mouth, Fujian and the Pearl River to Leizhou and Hainan
    (Hong Kong + Macao counted as land). Filled land polygons clipped to the
    box, plus the open coastline for the stroke and for the inland fade mask
    the component builds (so the box's straight cuts never show).
  * TAIWAN — the main island plus Penghu, Green Island and Lanyu, filled.

Natural Earth 10m admin0. Output: frontend/src/components/mastheadEmblems.js
(committed; re-run only to retune). `--cache DIR` keeps the ~25 MB download
between tolerance passes:

    python scripts/build_masthead_emblems.py [--cache DIR]
"""
from __future__ import annotations
import json
import math
import sys
import urllib.request
from pathlib import Path

NE_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
          "master/geojson/ne_10m_admin_0_countries.geojson")
OUT = Path("frontend/src/components/mastheadEmblems.js")

# Every emblem is projected to a fixed viewBox HEIGHT; width follows from the
# box aspect (equirectangular, cos-lat corrected at the box centre). The
# component scales by CSS height, so H only sets path precision.
H = 100.0

EMBLEMS = {
    # bbox lon0, lat0, lon1, lat1. Top cuts across the Bohai so the Shandong
    # peninsula reads as a peninsula; bottom clears Hainan; west edge stops
    # before the Vietnamese coast (which at 17.8 N sits at ~106.5 E) and the
    # east edge stops before Yonaguni. North Korea's coast at 38.2 N is
    # beyond 124 E — outside.
    "MAINLAND": dict(bbox=(108.3, 17.8, 123.5, 38.2),
                     admins=("China", "Hong Kong S.A.R.", "Macao S.A.R."),
                     eps=0.06,          # DP tolerance, degrees (~0.3 px at this scale)
                     min_span=0.35,     # drop islets below this lon/lat span (deg)
                     coast=True),
    "TAIWAN": dict(bbox=(119.2, 21.8, 122.1, 25.4),
                   admins=("Taiwan",),
                   eps=0.008,
                   min_span=0.045,     # Penghu (Magong/Huxi, Xiyu, Baisha), Green Island, Lanyu
                   # 外傘頂洲 — the Waisanding sandbar off Chiayi. A shifting bar,
                   # not a place; at emblem scale it reads as a spike on the coast.
                   drop_boxes=[(120.0, 23.4, 120.15, 23.55)],
                   coast=False),
}


def dp(points, eps):
    if len(points) < 3:
        return list(points)
    (x1, y1), (x2, y2) = points[0], points[-1]
    dmax, idx = 0.0, 0
    den = math.hypot(x2 - x1, y2 - y1)
    for i in range(1, len(points) - 1):
        x0, y0 = points[i]
        d = (math.hypot(x0 - x1, y0 - y1) if den == 0
             else abs((y2 - y1) * x0 - (x2 - x1) * y0 + x2 * y1 - y2 * x1) / den)
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        return dp(points[: idx + 1], eps)[:-1] + dp(points[idx:], eps)
    return [points[0], points[-1]]


def clip_ring(ring, bbox):
    """Sutherland–Hodgman against the bbox rectangle. Returns the clipped ring
    (may be empty)."""
    x0, y0, x1, y1 = bbox
    edges = (
        (lambda p: p[0] >= x0, lambda a, b: (x0, a[1] + (b[1] - a[1]) * (x0 - a[0]) / (b[0] - a[0]))),
        (lambda p: p[0] <= x1, lambda a, b: (x1, a[1] + (b[1] - a[1]) * (x1 - a[0]) / (b[0] - a[0]))),
        (lambda p: p[1] >= y0, lambda a, b: (a[0] + (b[0] - a[0]) * (y0 - a[1]) / (b[1] - a[1]), y0)),
        (lambda p: p[1] <= y1, lambda a, b: (a[0] + (b[0] - a[0]) * (y1 - a[1]) / (b[1] - a[1]), y1)),
    )
    out = list(ring)
    for inside, intersect in edges:
        if not out:
            return []
        inp, out = out, []
        prev = inp[-1]
        for cur in inp:
            if inside(cur):
                if not inside(prev):
                    out.append(intersect(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(intersect(prev, cur))
            prev = cur
    return out


def coast_runs(ring, bbox):
    """Contiguous runs of ORIGINAL ring points inside the box — the coastline
    without the box's cut edges. A ring wholly inside comes back as one
    closed run."""
    x0, y0, x1, y1 = bbox
    inside = [x0 <= lon <= x1 and y0 <= lat <= y1 for lon, lat in ring]
    if all(inside):
        return [list(ring) + [ring[0]]]
    # rotate so we start just after an outside point → runs don't wrap
    start = inside.index(False)
    pts = ring[start:] + ring[:start]
    ins = inside[start:] + inside[:start]
    runs, cur = [], []
    for p, ok in zip(pts, ins):
        if ok:
            cur.append(p)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return [r for r in runs if len(r) >= 3]


def span(ring):
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return max(xs) - min(xs), max(ys) - min(ys)


class Proj:
    def __init__(self, bbox):
        self.bbox = bbox
        lat0 = (bbox[1] + bbox[3]) / 2
        self.k_lat = H / (bbox[3] - bbox[1])
        self.k_lon = self.k_lat * math.cos(math.radians(lat0))
        self.w = self.k_lon * (bbox[2] - bbox[0])

    def __call__(self, lon, lat):
        return (lon - self.bbox[0]) * self.k_lon, (self.bbox[3] - lat) * self.k_lat


def to_path(points, proj, close):
    pts = [proj(*p) for p in points]
    d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    return d + " Z" if close else d


def build(name, cfg, features):
    bbox = cfg["bbox"]
    proj = Proj(bbox)
    land, coast, kept = [], [], []
    for feat in features:
        admin = feat["properties"].get("ADMIN") or feat["properties"].get("NAME")
        if admin not in cfg["admins"]:
            continue
        geom = feat["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for poly in polys:
            outer = [tuple(p) for p in poly[0]]
            if outer[0] == outer[-1]:
                outer = outer[:-1]
            clipped = clip_ring(outer, bbox)
            if len(clipped) < 3:
                continue
            dx, dy = span(clipped)
            if max(dx, dy) < cfg["min_span"]:
                continue
            cx = sum(p[0] for p in clipped) / len(clipped)
            cy = sum(p[1] for p in clipped) / len(clipped)
            if any(x0 <= cx <= x1 and y0 <= cy <= y1 for x0, y0, x1, y1 in cfg.get("drop_boxes", ())):
                continue
            simp = dp(clipped + [clipped[0]], cfg["eps"])[:-1]
            if len(simp) < 3:
                continue
            land.append(to_path(simp, proj, close=True))
            kept.append(f"({cx:.2f},{cy:.2f}) {dx:.2f}x{dy:.2f}")
            if cfg["coast"]:
                for run in coast_runs(outer, bbox):
                    s = dp(run, cfg["eps"])
                    if len(s) >= 2:
                        coast.append(to_path(s, proj, close=False))
    print(f"{name}: {len(land)} land polygons ({sum(map(len, land))} chars), "
          f"{len(coast)} coast runs ({sum(map(len, coast))} chars); viewBox 0 0 {proj.w:.1f} {H:.0f}")
    print("   kept spans:", ", ".join(kept))
    return dict(viewBox=f"0 0 {proj.w:.1f} {H:.0f}", w=round(proj.w, 1), h=H,
                bbox=list(bbox), land=land, coast=coast)


def main(argv):
    cache = None
    if "--cache" in argv:
        cache = Path(argv[argv.index("--cache") + 1]) / "ne_10m_admin_0_countries.geojson"
    if cache and cache.exists():
        raw = cache.read_bytes()
    else:
        print(f"Fetching {NE_URL}")
        raw = urllib.request.urlopen(NE_URL).read()
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(raw)
    features = json.loads(raw)["features"]
    out = {name: build(name, cfg, features) for name, cfg in EMBLEMS.items()}
    js = ("// Auto-generated by scripts/build_masthead_emblems.py. Do not hand-edit.\n"
          "// Two independent silhouettes for the masthead flanks (MastheadCoasts.jsx),\n"
          "// each in its own viewBox / projection — they are emblems, not one map.\n"
          "// `land` = closed filled polygons (box-clipped); `coast` = open coastline\n"
          "// polylines WITHOUT the box's cut edges (stroke + inland-fade mask).\n\n")
    for name, emb in out.items():
        js += f"export const {name} = {json.dumps(emb)};\n"
    OUT.write_text(js, encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main(sys.argv[1:])
