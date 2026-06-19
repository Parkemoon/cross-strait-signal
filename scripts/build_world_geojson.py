"""Build the trimmed world choropleth basemap for the Diplomacy Tracker.

Fetches Natural Earth 1:110m Admin-0 countries (public domain) and writes a
slimmed GeoJSON to `frontend/public/geo/world-110m.geojson`, served as a
static asset and fetched at runtime by `DiplomacyMap.jsx`.

Why a build step (mirrors scripts/build_taiwan_strait_map.py): the raw NE
file is ~840 KB with dozens of properties we don't need. We keep only an
`iso_a2` join key + display `name`, round coordinates to 2 dp (~1 km — plenty
for a 1:110m world map), and drop Antarctica. That cuts the payload to a size
that's cheap to fetch on tab open.

The `iso_a2` join key: Natural Earth famously stamps ISO_A2 = "-99" for a
handful of entities (France, Norway, and disputed/partial-recognition cases).
ISO_A2_EH ("EH" = de-facto, with sovereignty fixes) repairs France/Norway, so
we prefer it and fall back to ISO_A2. Anything still "-99" (Kosovo, N. Cyprus,
Somaliland, …) is left without a join key — those aren't on the diplomacy
roster, so they simply render as no-data base fill, which is correct.

Re-run only to refresh the basemap (new NE release, precision change). Output
is committed so the frontend build has no network dependency.

    python scripts/build_world_geojson.py
"""
import json
import os
import sys
import urllib.request

NE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_110m_admin_0_countries.geojson"
)
OUT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "frontend", "public", "geo", "world-110m.geojson"
)
PRECISION = 2  # decimal places — ~1.1 km at the equator


def iso_a2(props: dict):
    """Best available ISO 3166-1 alpha-2, or None. See module docstring."""
    for key in ("ISO_A2_EH", "ISO_A2"):
        code = (props.get(key) or "").strip().upper()
        if code and code != "-99":
            return code
    return None


def round_coords(coords):
    """Recursively round every coordinate pair in a GeoJSON geometry."""
    if isinstance(coords, (int, float)):
        return round(coords, PRECISION)
    return [round_coords(c) for c in coords]


def main():
    print(f"Fetching {NE_URL} …", file=sys.stderr)
    with urllib.request.urlopen(NE_URL, timeout=60) as resp:
        raw = json.load(resp)

    out_features = []
    dropped = 0
    for feat in raw["features"]:
        props = feat.get("properties", {})
        name = props.get("NAME") or props.get("NAME_LONG")
        # Drop Antarctica — it eats the bottom of the map and is never on roster.
        if (props.get("ISO_A3") == "ATA") or name == "Antarctica":
            dropped += 1
            continue
        lx, ly = props.get("LABEL_X"), props.get("LABEL_Y")
        feat["properties"] = {
            "iso_a2": iso_a2(props),
            "name": name,
            # NE's cartographic label point — a sensible on-land anchor for the
            # voices-pin layer (avoids the bbox-centre-in-ocean problem for
            # countries like the US with far-flung territory).
            "lx": round(lx, 2) if lx is not None else None,
            "ly": round(ly, 2) if ly is not None else None,
        }
        feat["geometry"]["coordinates"] = round_coords(feat["geometry"]["coordinates"])
        # Strip bbox/id noise NE sometimes carries.
        feat.pop("bbox", None)
        out_features.append(feat)

    out = {"type": "FeatureCollection", "features": out_features}
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"), ensure_ascii=False)

    size_kb = os.path.getsize(OUT_PATH) / 1024
    joinable = sum(1 for f in out_features if f["properties"]["iso_a2"])
    print(
        f"Wrote {len(out_features)} features ({joinable} with iso_a2, "
        f"{dropped} dropped) → {os.path.relpath(OUT_PATH)} ({size_kb:.0f} KB)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
