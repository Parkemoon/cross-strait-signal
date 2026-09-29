// CARTO raster basemap — single source of truth for the four Leaflet maps
// (ExerciseMap, CoastGuardMap, VisitsMap, DiplomacyMap). Since 2026-09-23
// CARTO watermarks keyless tiles "API KEY REQUIRED", so the key is inlined
// at build time from REACT_APP_CARTO_KEY in the server .env (server_deploy.sh
// exports it to both the admin and public builds). Without it the maps still
// render, but every tile carries the watermark. Attribution is mandatory on
// the free tier.
const CARTO_KEY = process.env.REACT_APP_CARTO_KEY || "";

export function cartoTileUrl(style) {
  const url = `https://{s}.basemaps.cartocdn.com/${style}/{z}/{x}/{y}.png`;
  return CARTO_KEY ? `${url}?key=${encodeURIComponent(CARTO_KEY)}` : url;
}

export const CARTO_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';
