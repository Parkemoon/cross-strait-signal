import { useEffect, useRef } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { READ_ONLY } from "../readOnly";

// Pans/zooms the map to a selected marker and opens its popup. Lives
// inside MapContainer so it can grab the Leaflet Map instance via
// useMap(). Receives the marker ref map by ref-object so opening the
// popup goes through the existing <CircleMarker> + <Popup> binding —
// no need to re-render the popup contents here.
function FlyToSelected({ targetId, rows, markerRefs }) {
  const map = useMap();
  useEffect(() => {
    if (!targetId) return undefined;
    const target = rows.find((r) => r.id === targetId);
    if (!target || typeof target.latitude !== "number") return undefined;
    map.flyTo([target.latitude, target.longitude], Math.max(map.getZoom(), 7), {
      duration: 0.6,
    });
    // Defer popup-open so the flyTo animation places the popup at the
    // moved-to centre. The cleanup cancels the pending open if the
    // user clicks another list row or the component unmounts before
    // the timer fires, which prevents openPopup() on a detached marker.
    const t = setTimeout(() => {
      const marker = markerRefs.current[targetId];
      if (marker && marker._map) marker.openPopup();
    }, 200);
    return () => clearTimeout(t);
  }, [targetId, rows, map, markerRefs]);
  return null;
}

// Locked performer palette (matches the project's party-colour scheme where
// it overlaps; MULTI is grey because it has no single owner).
export const PERFORMER_COLOUR = {
  PRC:   "#dc2626",
  ROC:   "#16a34a",
  US:    "#1d4ed8",
  JP:    "#14B8A6",
  MULTI: "#6b7280",
};

export const PERFORMER_LABEL = {
  PRC:   "PRC",
  ROC:   "Taiwan",
  US:    "US",
  JP:    "Japan",
  MULTI: "Multilateral",
};

// Default bbox when no geocoded exercises exist — TW Strait + Senkaku +
// N. SCS. Leaflet expects [[south, west], [north, east]].
const REGIONAL_BOUNDS = [[8, 108], [30, 127]];
// Hard ceiling — maxBounds restricts panning to a generous Indo-Pacific
// rectangle, large enough to include every entry in military_locations.json
// (Yokosuka 35.29/139.66, Guam 13.45/144.78, Hainan/Yulin 18.22/109.69).
// The map fits to actual markers within these limits.
const MAX_BOUNDS = [[2, 100], [42, 148]];

function boundsForRows(rows) {
  const geo = rows.filter(
    (r) => typeof r.latitude === "number" && typeof r.longitude === "number",
  );
  if (geo.length === 0) return REGIONAL_BOUNDS;
  let minLat = Infinity, maxLat = -Infinity, minLng = Infinity, maxLng = -Infinity;
  for (const r of geo) {
    if (r.latitude < minLat) minLat = r.latitude;
    if (r.latitude > maxLat) maxLat = r.latitude;
    if (r.longitude < minLng) minLng = r.longitude;
    if (r.longitude > maxLng) maxLng = r.longitude;
  }
  // Pad ~1° each side so markers aren't clipped to the viewport edge.
  // Also union with the regional bbox so single-marker views aren't
  // disorientingly zoomed-in.
  const pad = 1;
  return [
    [Math.min(minLat - pad, REGIONAL_BOUNDS[0][0]),
     Math.min(minLng - pad, REGIONAL_BOUNDS[0][1])],
    [Math.max(maxLat + pad, REGIONAL_BOUNDS[1][0]),
     Math.max(maxLng + pad, REGIONAL_BOUNDS[1][1])],
  ];
}

function fmtDateRange(start, end) {
  if (!start && !end) return "—";
  if (!end || end === start) return start || "";
  return `${start} → ${end}`;
}

// Inline-styled icon button for popup actions. Popups render on a white
// Leaflet-default background, so colours are hardcoded rather than theme
// variables (which would be invisible against the popup chrome).
function PopupIconButton({ title, onClick, colour, children }) {
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      title={title}
      style={{
        background: "transparent",
        border: `1px solid ${colour || "#bbb"}`,
        color: colour || "#555",
        cursor: "pointer",
        padding: "2px 8px",
        fontSize: "11px",
        lineHeight: 1.2,
        fontFamily: "var(--font-mono)",
      }}
    >
      {children}
    </button>
  );
}

function MarkerPopup({ exercise, onEdit, onQuickDismiss }) {
  const { name_en, name_zh, performer, exercise_kind,
          start_date, end_date, location_label,
          description_en, article, participants } = exercise;
  const displayName = name_en || (
    name_zh
      ? `${name_zh} (no English name)`
      : `${PERFORMER_LABEL[performer]} ${(exercise_kind || "other").replace("_", " ")}`
  );
  return (
    <div style={{
      fontFamily: "var(--font-mono)",
      fontSize: "11px",
      lineHeight: 1.45,
      minWidth: "210px",
      maxWidth: "260px",
    }}>
      <div style={{
        fontFamily: "var(--font-display, serif)",
        fontSize: "13px",
        fontWeight: 600,
        color: "#222",
        marginBottom: "4px",
      }}>
        {displayName}
      </div>
      <div style={{ color: "#666", marginBottom: "2px" }}>
        <strong style={{ color: PERFORMER_COLOUR[performer] }}>
          {PERFORMER_LABEL[performer]}
        </strong>
        {participants && participants.length > 0 && (
          <span> · {participants.join(" + ")}</span>
        )}
        <span> · {(exercise_kind || "other").replace("_", " ")}</span>
      </div>
      <div style={{ color: "#666" }}>{fmtDateRange(start_date, end_date)}</div>
      {location_label && (
        <div style={{ color: "#666", marginTop: "2px" }}>{location_label}</div>
      )}
      {description_en && (
        <div style={{
          marginTop: "6px",
          paddingTop: "6px",
          borderTop: "1px dotted #ccc",
          fontFamily: "var(--font-body, system-ui)",
          fontSize: "12px",
          color: "#333",
        }}>
          {description_en}
        </div>
      )}
      {article?.url && (
        <div style={{ marginTop: "6px" }}>
          <a href={article.url} target="_blank" rel="noreferrer"
             style={{ color: "#1d4ed8", textDecoration: "underline" }}>
            {article.source_name || "source"}
          </a>
        </div>
      )}
      {!READ_ONLY && (onEdit || onQuickDismiss) && (
        <div style={{
          marginTop: "8px",
          paddingTop: "6px",
          borderTop: "1px dotted #ccc",
          display: "flex",
          gap: "6px",
        }}>
          {onEdit && (
            <PopupIconButton title="Edit this exercise"
                             onClick={() => onEdit(exercise)}>
              ✎ Edit
            </PopupIconButton>
          )}
          {onQuickDismiss && (
            <PopupIconButton title="Dismiss this exercise"
                             colour="#dc2626"
                             onClick={() => onQuickDismiss(exercise)}>
              ✕ Dismiss
            </PopupIconButton>
          )}
        </div>
      )}
    </div>
  );
}

export default function ExerciseMap({ rows, selectedId, onEdit, onQuickDismiss }) {
  const geoRows = (rows || []).filter(
    (r) => typeof r.latitude === "number" && typeof r.longitude === "number",
  );

  // React 18+ Strict Mode double-mounts components in dev. Leaflet stamps
  // the DOM container with `_leaflet_id` on first init and refuses to
  // re-init the same element. Clearing the stamp on the fake-unmount
  // cleanup lets the immediate re-mount succeed. Production builds don't
  // double-mount, so this is purely a dev-mode guard.
  const wrapperRef = useRef(null);
  useEffect(() => () => {
    const container = wrapperRef.current?.querySelector(".leaflet-container");
    if (container && container._leaflet_id) {
      delete container._leaflet_id;
    }
  }, []);

  // Collect Leaflet marker refs keyed by exercise id so FlyToSelected can
  // open the right one's popup on click in the side list.
  const markerRefs = useRef({});

  return (
    <div ref={wrapperRef} style={{
      height: "460px",
      width: "100%",
      border: "1px solid var(--border-color)",
      background: "var(--bg-card)",
      position: "relative",
    }}>
      <MapContainer
        bounds={boundsForRows(rows || [])}
        maxBounds={MAX_BOUNDS}
        scrollWheelZoom={false}
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer
          // CartoDB Positron — free raster tiles, no API key. Attribution
          // is required (rendered automatically by Leaflet's default
          // attribution control); we set it on the TileLayer.
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          subdomains="abcd"
          maxZoom={11}
          minZoom={4}
        />
        {geoRows.map((ex) => {
          const isSelected = ex.id === selectedId;
          return (
            <CircleMarker
              key={ex.id}
              center={[ex.latitude, ex.longitude]}
              radius={isSelected ? 10 : 7}
              ref={(m) => {
                if (m) markerRefs.current[ex.id] = m;
                else delete markerRefs.current[ex.id];
              }}
              pathOptions={{
                color: PERFORMER_COLOUR[ex.performer] || "#666",
                fillColor: PERFORMER_COLOUR[ex.performer] || "#666",
                fillOpacity: isSelected ? 0.85 : 0.65,
                weight: isSelected ? 2.2 : 1.4,
              }}
            >
              <Popup>
                <MarkerPopup exercise={ex}
                             onEdit={onEdit}
                             onQuickDismiss={onQuickDismiss} />
              </Popup>
            </CircleMarker>
          );
        })}
        <FlyToSelected targetId={selectedId} rows={geoRows} markerRefs={markerRefs} />
      </MapContainer>
      {geoRows.length === 0 && (
        <div style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          pointerEvents: "none",
          fontFamily: "var(--font-mono)",
          fontSize: "11px",
          color: "var(--text-muted)",
          background: "rgba(248, 246, 240, 0.55)",
        }}>
          No geo-located exercises in this window.
        </div>
      )}
    </div>
  );
}
