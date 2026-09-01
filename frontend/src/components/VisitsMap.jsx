import { useEffect, useMemo, useRef } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { DIR_COLOUR, DIRECTION_LABEL } from "./VisitsReviewQueue";

// Visits map — one marker per (place, direction), sized by visit count.
// `cross_strait_visits` stores only a free-text `location_label` (city or
// venue in English, per the extraction prompt), so places resolve through
// this hand-curated gazetteer rather than per-row geocoding. Unresolvable
// labels ("Mainland China", null) stay list-only — same convention as the
// exercise map's ungeocoded rows. Multi-leg labels ("Nanjing, Shanghai,
// Beijing") pin on the FIRST resolvable leg.
const PLACES = {
  // PRC
  beijing: [39.9, 116.41], shanghai: [31.23, 121.47], nanjing: [32.06, 118.78],
  jiangsu: [32.06, 118.78], hangzhou: [30.27, 120.16], zhejiang: [30.27, 120.16],
  xiamen: [24.48, 118.09], fuzhou: [26.07, 119.3], pingtan: [25.5, 119.79],
  fujian: [26.07, 119.3], guangzhou: [23.13, 113.26], shenzhen: [22.54, 114.06],
  guangdong: [23.13, 113.26], zhuhai: [22.27, 113.58], tianjin: [39.08, 117.2],
  chongqing: [29.56, 106.55], chengdu: [30.57, 104.07], sichuan: [30.57, 104.07],
  wuhan: [30.59, 114.31], hubei: [30.59, 114.31], changsha: [28.23, 112.94],
  hunan: [28.23, 112.94], kunming: [25.04, 102.71], yunnan: [25.04, 102.71],
  dali: [25.61, 100.27], "xi'an": [34.34, 108.94], xian: [34.34, 108.94],
  shaanxi: [34.34, 108.94], zhengzhou: [34.75, 113.63], henan: [34.75, 113.63],
  qingdao: [36.07, 120.38], jinan: [36.65, 117.12], shandong: [36.65, 117.12],
  qufu: [35.6, 116.99], dalian: [38.91, 121.6], shenyang: [41.8, 123.43],
  harbin: [45.8, 126.53], nanchang: [28.68, 115.86], hefei: [31.82, 117.23],
  suzhou: [31.3, 120.58], wuxi: [31.49, 120.31], ningbo: [29.87, 121.54],
  wenzhou: [28.0, 120.67], guilin: [25.28, 110.29], nanning: [22.82, 108.37],
  haikou: [20.04, 110.34], sanya: [18.25, 109.51], hainan: [20.04, 110.34],
  lanzhou: [36.06, 103.83], guiyang: [26.65, 106.63],
  // HK / Macao
  "hong kong": [22.32, 114.17], macau: [22.2, 113.55], macao: [22.2, 113.55],
  // Taiwan
  taipei: [25.03, 121.57], "new taipei": [25.01, 121.46], taoyuan: [24.99, 121.3],
  hsinchu: [24.8, 120.97], taichung: [24.15, 120.67], changhua: [24.08, 120.54],
  nantou: [23.91, 120.69], "sun moon lake": [23.86, 120.92], yunlin: [23.71, 120.43],
  chiayi: [23.48, 120.45], tainan: [22.99, 120.21], kaohsiung: [22.63, 120.3],
  pingtung: [22.68, 120.49], yilan: [24.76, 121.75], hualien: [23.98, 121.6],
  taitung: [22.75, 121.15], keelung: [25.13, 121.74], kinmen: [24.43, 118.32],
  matsu: [26.16, 119.95], lienchiang: [26.16, 119.95], penghu: [23.57, 119.58],
  // Third venues
  singapore: [1.35, 103.82],
};

const _STRIP = /\s+(city|province|county|district)$/;

export function resolvePlace(label) {
  if (!label) return null;
  const whole = label.trim().toLowerCase();
  if (PLACES[whole]) return { name: label.trim(), ll: PLACES[whole] };
  for (const part of whole.split(/[,、;/]| and /)) {
    const p = part.trim().replace(_STRIP, "");
    if (PLACES[p]) return { name: p.replace(/\b\w/g, (c) => c.toUpperCase()), ll: PLACES[p] };
  }
  return null;
}

// Default view: the strait + coastal PRC. Markers can extend it (Beijing,
// Singapore) via boundsFor's union.
const REGIONAL_BOUNDS = [[21.5, 112], [32, 124]];
const MAX_BOUNDS = [[-6, 90], [50, 145]];

function boundsFor(markers) {
  if (!markers.length) return REGIONAL_BOUNDS;
  let s = REGIONAL_BOUNDS[0][0], w = REGIONAL_BOUNDS[0][1],
      n = REGIONAL_BOUNDS[1][0], e = REGIONAL_BOUNDS[1][1];
  for (const m of markers) {
    s = Math.min(s, m.lat - 1); w = Math.min(w, m.lng - 1);
    n = Math.max(n, m.lat + 1); e = Math.max(e, m.lng + 1);
  }
  return [[s, w], [n, e]];
}

export default function VisitsMap({ visits }) {
  // Aggregate to one marker per (place, direction); the two directions at
  // one city get a small longitude offset so both stay clickable.
  const markers = useMemo(() => {
    const by = {};
    let unmapped = 0;
    for (const v of visits || []) {
      const place = resolvePlace(v.location_label);
      if (!place) { unmapped += 1; continue; }
      const key = `${place.name}|${v.direction}`;
      const m = by[key] || (by[key] = {
        key, name: place.name, direction: v.direction,
        lat: place.ll[0], lng: place.ll[1] + (v.direction === "PRC_TO_TW" ? 0.35 : 0),
        items: [],
      });
      m.items.push(v);
    }
    return { list: Object.values(by).sort((a, b) => b.items.length - a.items.length), unmapped };
  }, [visits]);

  // React StrictMode double-mount guard (same as ExerciseMap): clear
  // Leaflet's container stamp on the fake unmount so re-init succeeds.
  const wrapperRef = useRef(null);
  useEffect(() => () => {
    const container = wrapperRef.current?.querySelector(".leaflet-container");
    if (container && container._leaflet_id) delete container._leaflet_id;
  }, []);

  return (
    <div ref={wrapperRef} style={{ height: "380px", width: "100%", border: "1px solid var(--border-color)",
                                   background: "var(--bg-card)", position: "relative", marginBottom: "14px" }}>
      <MapContainer bounds={boundsFor(markers.list)} maxBounds={MAX_BOUNDS} scrollWheelZoom={false}
                    style={{ height: "100%", width: "100%" }}>
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          subdomains="abcd" maxZoom={11} minZoom={3} />
        {markers.list.map((m) => (
          <CircleMarker key={m.key} center={[m.lat, m.lng]}
                        radius={Math.min(6 + 3 * Math.sqrt(m.items.length - 1), 18)}
                        pathOptions={{ color: DIR_COLOUR[m.direction] || "#666",
                                       fillColor: DIR_COLOUR[m.direction] || "#666",
                                       fillOpacity: 0.6, weight: 1.4 }}>
            <Popup>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", lineHeight: 1.5, minWidth: "200px", maxWidth: "260px" }}>
                <div style={{ fontFamily: "var(--font-display, serif)", fontSize: "13px", fontWeight: 600, color: "#222" }}>
                  {m.name}
                </div>
                <div style={{ color: DIR_COLOUR[m.direction], marginBottom: "4px" }}>
                  {DIRECTION_LABEL[m.direction] || m.direction} · {m.items.length} visit{m.items.length > 1 ? "s" : ""}
                </div>
                {m.items.slice(0, 6).map((v) => (
                  <div key={v.id} style={{ color: "#333" }}>
                    {(v.start_date || v.effective_date || "").slice(0, 10)} · {v.visitor_name_en || v.visitor_name_zh || v.delegation_desc_en}
                    {v.visit_status !== "reported" ? <span style={{ color: "var(--flag)" }}> ({v.visit_status})</span> : null}
                  </div>
                ))}
                {m.items.length > 6 && <div style={{ color: "#888" }}>+{m.items.length - 6} more — see the timeline</div>}
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
      {markers.list.length === 0 && (
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
                      pointerEvents: "none", fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-muted)",
                      background: "rgba(248, 246, 240, 0.55)" }}>
          No mappable visit locations in this window.
        </div>
      )}
      {markers.unmapped > 0 && (
        <div style={{ position: "absolute", left: 8, bottom: 8, zIndex: 500, background: "var(--bg-primary)",
                      border: "1px solid var(--border-color)", padding: "4px 8px",
                      fontFamily: "var(--font-mono)", fontSize: "9.5px", color: "var(--text-muted)" }}>
          {markers.unmapped} visit{markers.unmapped > 1 ? "s" : ""} without a mappable place — timeline only
        </div>
      )}
    </div>
  );
}
