import { useEffect, useRef } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";

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

// Regional bbox — TW Strait + Senkaku + N. SCS. Matches the plan's locked
// scope (108–127°E, 8–30°N). Leaflet expects [[south, west], [north, east]].
const REGIONAL_BOUNDS = [[8, 108], [30, 127]];

function fmtDateRange(start, end) {
  if (!start && !end) return "—";
  if (!end || end === start) return start || "";
  return `${start} → ${end}`;
}

function MarkerPopup({ exercise }) {
  const { name_en, name_zh, performer, exercise_kind,
          start_date, end_date, location_label,
          description_en, article, participants } = exercise;
  const displayName = name_en || (
    name_zh
      ? `${name_zh} (no English name)`
      : `${PERFORMER_LABEL[performer]} ${exercise_kind.replace("_", " ")}`
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
        <span> · {exercise_kind.replace("_", " ")}</span>
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
    </div>
  );
}

export default function ExerciseMap({ rows }) {
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

  return (
    <div ref={wrapperRef} style={{
      height: "460px",
      width: "100%",
      border: "1px solid var(--border-color)",
      background: "var(--bg-card)",
      position: "relative",
    }}>
      <MapContainer
        bounds={REGIONAL_BOUNDS}
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
        {geoRows.map((ex) => (
          <CircleMarker
            key={ex.id}
            center={[ex.latitude, ex.longitude]}
            radius={7}
            pathOptions={{
              color: PERFORMER_COLOUR[ex.performer] || "#666",
              fillColor: PERFORMER_COLOUR[ex.performer] || "#666",
              fillOpacity: 0.65,
              weight: 1.4,
            }}
          >
            <Popup>
              <MarkerPopup exercise={ex} />
            </Popup>
          </CircleMarker>
        ))}
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
