import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, TileLayer, GeoJSON, CircleMarker, Tooltip } from "react-leaflet";
import "leaflet/dist/leaflet.css";

// Diverging stance ramp for the third-country axis (pro-Beijing ↔ pro-Taipei).
// This is a SEPARATE axis from the core cross-strait sentiment instrument
// (purple/amber), so it deliberately reuses the locked side conventions —
// PRC red, ROC/Taipei green — which read instantly on a world map. Tuned to
// sit on the light CartoDB Positron basemap, not the app's parchment.
export const BAND_COLOUR = {
  pro_taipei:      "#1a8043",
  leaning_taipei:  "#8fc9a3",
  neutral:         "#9aa0a6",
  leaning_beijing: "#e79a93",
  pro_beijing:     "#c1272d",
};

export const BAND_LABEL = {
  pro_taipei:      "Pro-Taipei",
  leaning_taipei:  "Leaning Taipei",
  neutral:         "Neutral",
  leaning_beijing: "Leaning Beijing",
  pro_beijing:     "Pro-Beijing",
};

export const BAND_ORDER = [
  "pro_taipei", "leaning_taipei", "neutral", "leaning_beijing", "pro_beijing",
];

// authority_tier → display label. Shared by DiplomacyTab + DiplomacyReviewQueue
// (mirrors _VALID_AUTHORITY_TIERS in scraper/processors/ai_pipeline.py).
export const TIER_LABEL = {
  government:      "Government",
  head_of_state:   "Head of state",
  ruling_party:    "Ruling party",
  legislator:      "Legislator",
  subnational:     "Subnational",
  former_official: "Former official",
  other:           "Other",
};

// Country in the /map response but with no official-tier fill (pins only):
// "we hear voices here but no national posture on record".
const PINS_ONLY_FILL = "#d2ccbb";
// Country absent from the response entirely (un-tracked in window).
const NO_DATA_FILL = "#ece7db";
const NO_DATA_STROKE = "#c7c0ad";
// Analyst-flagged divergence (a non-official voice opposing the official
// fill) — gold dashed outline, the app's existing review-accent colour.
const DIVERGENT_STROKE = "#d4a94a";
const SELECTED_STROKE = "#2e2010"; // warm umber — matches header

// Roster countries Natural Earth 1:110m has no polygon for (sub-pixel
// microstates + city-states). Several are Taiwan's diplomatic allies, so they
// must not silently vanish from the map — they render as centroid markers,
// which doubles as a preview of the eventual per-statement pins layer.
const MICROSTATE_CENTROIDS = {
  SG: [1.35, 103.82],   // Singapore
  VA: [41.90, 12.45],   // Holy See (Vatican)
  PW: [7.51, 134.58],   // Palau
  MH: [7.13, 171.18],   // Marshall Islands
  NR: [-0.52, 166.93],  // Nauru
  TV: [-8.52, 179.20],  // Tuvalu
  KI: [1.33, 172.98],   // Kiribati
  KN: [17.30, -62.73],  // Saint Kitts and Nevis
  LC: [13.91, -60.98],  // Saint Lucia
  VC: [13.25, -61.20],  // Saint Vincent and the Grenadines
};

// Fill colour for a country given its /map entry (or undefined = un-tracked).
function fillFor(country) {
  if (!country) return NO_DATA_FILL;
  if (!country.fill) return PINS_ONLY_FILL;
  return BAND_COLOUR[country.fill.stance_label] || BAND_COLOUR.neutral;
}

// StrictMode dev double-mount guard — see ExerciseMap.jsx for the rationale.
function useLeafletRemountGuard(wrapperRef) {
  useEffect(() => () => {
    const container = wrapperRef.current?.querySelector(".leaflet-container");
    if (container && container._leaflet_id) delete container._leaflet_id;
  }, [wrapperRef]);
}

export default function DiplomacyMap({ countries, selectedIso, onSelect, showPins = true, height = 520 }) {
  const wrapperRef = useRef(null);
  useLeafletRemountGuard(wrapperRef);

  const [geo, setGeo] = useState(null);
  const [geoError, setGeoError] = useState(false);

  // Basemap is a static asset (built by scripts/build_world_geojson.py),
  // fetched once when the tab first mounts the map.
  useEffect(() => {
    let alive = true;
    fetch("/geo/world-110m.geojson")
      .then((r) => { if (!r.ok) throw new Error(`geojson ${r.status}`); return r.json(); })
      .then((d) => { if (alive) setGeo(d); })
      .catch(() => { if (alive) setGeoError(true); });
    return () => { alive = false; };
  }, []);

  // iso (alpha-2) → /map country entry.
  const byIso = useMemo(() => {
    const m = new Map();
    for (const c of countries || []) m.set(c.country_iso, c);
    return m;
  }, [countries]);

  // iso → [lat, lng] anchor for the voices-pin layer, from NE label points.
  const labelPoints = useMemo(() => {
    const m = new Map();
    if (geo) {
      for (const f of geo.features) {
        const { iso_a2, lx, ly } = f.properties;
        if (iso_a2 && typeof lx === "number" && typeof ly === "number") m.set(iso_a2, [ly, lx]);
      }
    }
    return m;
  }, [geo]);

  // Re-key the base GeoJSON layer when the fill data changes so Leaflet
  // restyles every polygon (the `style` callback is only read at mount).
  // Selection is handled by a separate overlay layer, so clicking a country
  // does NOT remount this one.
  const dataVersion = useMemo(
    () => (countries || []).map((c) => `${c.country_iso}:${c.fill?.stance_label || "_"}:${c.divergent ? "d" : ""}`).join("|"),
    [countries],
  );

  const styleFeature = (feature) => {
    const country = byIso.get(feature.properties.iso_a2);
    const divergent = country?.divergent;
    return {
      fillColor: fillFor(country),
      fillOpacity: country ? (country.fill ? 0.82 : 0.5) : 0.55,
      color: divergent ? DIVERGENT_STROKE : NO_DATA_STROKE,
      weight: divergent ? 1.8 : 0.5,
      dashArray: divergent ? "4 3" : undefined,
    };
  };

  const onEachFeature = (feature, layer) => {
    const iso = feature.properties.iso_a2;
    const country = byIso.get(iso);
    const name = country?.country_name || feature.properties.name || iso;
    const detail = country
      ? (country.fill
          ? `${BAND_LABEL[country.fill.stance_label]}${country.divergent ? " · divergence flagged" : ""}`
          : `${country.pins_count} non-official voice${country.pins_count === 1 ? "" : "s"} · no official posture`)
      : "Not tracked in this window";
    layer.bindTooltip(
      `<span style="font-family:var(--font-mono);font-size:11px">` +
      `<strong>${name}</strong><br/>${detail}</span>`,
      { sticky: true, direction: "auto" },
    );
    layer.on({
      mouseover: (e) => e.target.setStyle({ weight: 2, fillOpacity: 0.92 }),
      mouseout: (e) => e.target.setStyle(styleFeature(feature)),
      click: () => { if (country && onSelect) onSelect(iso); },
    });
  };

  // The single selected feature, rendered as a bold non-interactive overlay so
  // selection never remounts the base layer.
  const selectedFeature = useMemo(() => {
    if (!geo || !selectedIso) return null;
    return geo.features.find((f) => f.properties.iso_a2 === selectedIso) || null;
  }, [geo, selectedIso]);

  return (
    <div ref={wrapperRef} style={{
      height: `${height}px`,
      width: "100%",
      border: "1px solid var(--border-color)",
      background: "var(--bg-card)",
      position: "relative",
    }}>
      <MapContainer
        center={[22, 30]}
        zoom={2}
        minZoom={1}
        maxZoom={6}
        worldCopyJump
        maxBounds={[[-72, -200], [88, 200]]}
        scrollWheelZoom={false}
        style={{ height: "100%", width: "100%", background: "#dfe6ea" }}
      >
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          subdomains="abcd"
          maxZoom={6}
          minZoom={1}
          noWrap={false}
        />
        {geo && (
          <GeoJSON
            key={dataVersion}
            data={geo}
            style={styleFeature}
            onEachFeature={onEachFeature}
          />
        )}
        {selectedFeature && (
          <GeoJSON
            key={`sel-${selectedIso}`}
            data={selectedFeature}
            interactive={false}
            style={{ fillOpacity: 0, color: SELECTED_STROKE, weight: 2.4 }}
          />
        )}
        {/* Microstate markers — roster allies NE-110m omits as polygons. */}
        {(countries || [])
          .filter((c) => MICROSTATE_CENTROIDS[c.country_iso])
          .map((c) => {
            const pos = MICROSTATE_CENTROIDS[c.country_iso];
            const colour = fillFor(c);
            const isSel = c.country_iso === selectedIso;
            return (
              <CircleMarker
                key={c.country_iso}
                center={pos}
                radius={isSel ? 7 : 5}
                pathOptions={{
                  color: c.divergent ? DIVERGENT_STROKE : (isSel ? SELECTED_STROKE : "#5b5346"),
                  weight: c.divergent ? 1.8 : (isSel ? 2.2 : 1),
                  dashArray: c.divergent ? "4 3" : undefined,
                  fillColor: colour,
                  fillOpacity: 0.9,
                }}
                eventHandlers={{ click: () => onSelect && onSelect(c.country_iso) }}
              >
                <Tooltip sticky direction="auto">
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px" }}>
                    <strong>{c.country_name}</strong>
                    {c.fill ? ` · ${BAND_LABEL[c.fill.stance_label]}` : ` · ${c.pins_count} voice(s)`}
                  </span>
                </Tooltip>
              </CircleMarker>
            );
          })}

        {/* Voices-pin layer — non-official voices (legislators, parties,
            sub-national) at each polygon country's label point, coloured by
            their aggregate stance. A green pin on a red fill = the divergence
            headline made visible. Microstates already render as a single
            marker above, so they're excluded here to avoid stacking. */}
        {showPins && (countries || [])
          .filter((c) => c.pins_count > 0
            && !MICROSTATE_CENTROIDS[c.country_iso]
            && labelPoints.has(c.country_iso))
          .map((c) => {
            const pos = labelPoints.get(c.country_iso);
            const colour = BAND_COLOUR[c.pins_label] || "#9aa0a6";
            return (
              <CircleMarker
                key={`pin-${c.country_iso}`}
                center={pos}
                radius={c.divergent ? 6 : 5}
                pathOptions={{
                  color: c.divergent ? DIVERGENT_STROKE : "#1f2937",
                  weight: c.divergent ? 2.4 : 1,
                  fillColor: colour,
                  fillOpacity: 0.95,
                }}
                eventHandlers={{ click: () => onSelect && onSelect(c.country_iso) }}
              >
                <Tooltip direction="top">
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px" }}>
                    <strong>{c.country_name}</strong> · {c.pins_count} non-official voice{c.pins_count === 1 ? "" : "s"}
                    {c.pins_label ? ` · ${BAND_LABEL[c.pins_label]}` : ""}
                    {c.divergent ? " · ◆ divergence" : ""}
                  </span>
                </Tooltip>
              </CircleMarker>
            );
          })}
      </MapContainer>
      {geoError && (
        <div style={{
          position: "absolute", inset: 0, display: "flex",
          alignItems: "center", justifyContent: "center", pointerEvents: "none",
          fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-muted)",
          background: "rgba(248, 246, 240, 0.7)",
        }}>
          Couldn't load the world basemap.
        </div>
      )}
    </div>
  );
}
