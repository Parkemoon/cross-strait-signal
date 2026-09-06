import { useEffect, useState } from "react";
import { MapContainer, TileLayer, GeoJSON } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { fetchCoastGuardZones } from "../api";

// Zone polygons for the Coast Guard tracker. Fill intensity = CCG hull-days in
// the summary window (sequential, one hue — PRC red); the tooltip carries every
// force so the map never reads as a one-sided instrument. Stroke encodes the
// zone kind: prohibited = solid, restricted = dashed, everything else = dotted.
// Same react-leaflet v4 / StrictMode-off caveats as ExerciseMap.
// MaritimeCivilSection (Phase 2g) reuses the map with its own `value` (fill
// number per zone), `lines` (tooltip HTML per zone), `hue` and `legend`; the
// defaults below are the coast-guard reading so CoastGuardSection is unchanged.
// CCG red as a raw rgb triple for alpha fills. FORCE_COLOUR.CCG is now a
// var() token and can't be hex-sliced; the map sits on light tiles in both
// themes, so the light-mode --red (#b0392e) is pinned here as a literal.
const CCG_HUE = "176, 57, 46";
const KIND_STROKE = {
  prohibited: { weight: 1.8, dashArray: null },
  restricted: { weight: 1.4, dashArray: "5 4" },
  band:       { weight: 1.0, dashArray: "2 4" },
  sector:     { weight: 0.8, dashArray: "2 4" },
  radius:     { weight: 1.0, dashArray: "2 4" },
  box:        { weight: 0.8, dashArray: "8 4" },
  shoal:      { weight: 0.8, dashArray: "1 3" },    // Taiwan Bank analytical box (fine-dotted)
};
const cgValue = (z) => z?.forces?.CCG?.hull_days || 0;
const cgLines = (z) => {
  const line = (force, label) => {
    const s = z?.forces?.[force];
    return `<div>${label}: <b>${s ? s.hull_days : 0}</b> hull-days${s ? ` · ${s.hulls} hulls` : ""}</div>`;
  };
  return line("CCG", "China CG") + line("CGA", "Taiwan CG");
};
const CG_LEGEND = ["Fill: China CG hull-days in window · hover for both forces",
                   "Solid = prohibited · dashed = restricted · dotted = 12/24 nm bands"];
const BOUNDS = [[19.5, 115.5], [27.5, 124.5]];   // Kinmen → east-coast box

export default function CoastGuardMap({ zoneStats, height = 380, value = cgValue, lines = cgLines, hue = CCG_HUE, legend = CG_LEGEND }) {
  const [geo, setGeo] = useState(null);
  useEffect(() => {
    fetchCoastGuardZones({ geometry: true })
      .then((d) => setGeo({
        type: "FeatureCollection",
        features: (d.zones || []).map((z) => ({ type: "Feature", properties: z, geometry: z.geometry })),
      }))
      .catch(() => setGeo(null));
  }, []);

  const byZone = {};
  let max = 0;
  for (const z of zoneStats || []) {
    byZone[z.zone_id] = z;
    max = Math.max(max, value(z));
  }

  const styleFeature = (f) => {
    const p = f.properties;
    const v = byZone[p.id] ? value(byZone[p.id]) : 0;
    const t = max > 0 ? v / max : 0;
    const s = KIND_STROKE[p.kind] || KIND_STROKE.sector;
    return {
      color: `rgba(${hue}, 0.85)`, weight: s.weight, dashArray: s.dashArray,
      fillColor: `rgb(${hue})`, fillOpacity: v === 0 ? 0.04 : 0.12 + t * 0.5,
    };
  };

  const onEachFeature = (f, layer) => {
    const p = f.properties;
    const z = byZone[p.id] || null;
    layer.bindTooltip(
      `<div style="font-family:var(--font-mono);font-size:11px;line-height:1.5">` +
      `<div style="font-weight:700">${p.label_en}</div><div style="color:var(--muted)">${p.label_zh} · ${p.area_km2.toLocaleString()} km²</div>` +
      lines(z) + `</div>`,
      { sticky: true },
    );
  };

  return (
    <div style={{ height: `${height}px`, width: "100%", border: "1px solid var(--border-color)",
                  background: "var(--bg-card)", position: "relative" }}>
      <MapContainer bounds={BOUNDS} minZoom={5} maxZoom={10} scrollWheelZoom={false}
                    style={{ height: "100%", width: "100%", background: "#dfe6ea" }}>
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          subdomains="abcd" maxZoom={10} />
        {geo && (
          <GeoJSON key={`z-${max}-${(zoneStats || []).length}`} data={geo}
                   style={styleFeature} onEachFeature={onEachFeature} />
        )}
      </MapContainer>
      <div style={{ position: "absolute", left: 8, bottom: 8, zIndex: 500, background: "var(--bg-primary)",
                    border: "1px solid var(--border-color)", padding: "5px 8px",
                    fontFamily: "var(--font-mono)", fontSize: "9.5px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
        {legend.map((l) => <div key={l}>{l}</div>)}
      </div>
    </div>
  );
}
