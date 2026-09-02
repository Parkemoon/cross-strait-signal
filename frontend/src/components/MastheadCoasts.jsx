// The two sides of the strait flanking the nameplate (Ed's masthead idea,
// 2026-09-02): mainland coast + Kinmen / Matsu / Wuqiu on the WEST, Taiwan +
// Penghu / Lanyu / Green Island on the EAST, with the nameplate sitting where
// the strait is. One map, split along the Taiwan Strait Median Line, drawn at
// one shared scale so the two flanks stay geographically honest (Fujian sits
// north of Taiwan's bulk, so the west flank rides higher).
//
// Geometry is the Military tab's strait map (taiwanStraitMap.js — Natural
// Earth via scripts/build_taiwan_strait_map.py; viewBox 0 0 320 260 over
// lon 117–123.5 / lat 21–26.5). Nothing new is generated: each flank is a
// viewBox crop of that module clipped to its side of the median line, with the
// paths re-simplified at load for masthead scale (the module's ~2 km tolerance
// reads as a hairy squiggle at ~0.4 px per km).
// Colours are tokens (--ink / --soft / --muted) so light and dark just work.
// Decorative — aria-hidden; hidden by the caller on narrow viewports.
import React from "react";
import { TAIWAN_PATHS, PRC_COAST_PATHS } from "./taiwanStraitMap";

// Mirror of the builder's equirectangular projection (keep in lockstep with
// BBOX / SVG_W / SVG_H in scripts/build_taiwan_strait_map.py).
const BBOX = [117.0, 21.0, 123.5, 26.5];
const SVG_W = 320, SVG_H = 260;
const LAT0 = (BBOX[1] + BBOX[3]) / 2;
const PX_PER_DEG_LAT = SVG_H / (BBOX[3] - BBOX[1]);
const PX_PER_DEG_LON = PX_PER_DEG_LAT * Math.cos((LAT0 * Math.PI) / 180);
const X_OFFSET = (SVG_W - PX_PER_DEG_LON * (BBOX[2] - BBOX[0])) / 2;
const px = (lon, lat) => [X_OFFSET + (lon - BBOX[0]) * PX_PER_DEG_LON, (BBOX[3] - lat) * PX_PER_DEG_LAT];

// Median Line (Davis Line) as MND publishes it; extended along its own slope
// so the split covers the whole latitude range.
const MEDIAN_N = [122.0, 27.0], MEDIAN_S = [117.85, 23.283];
const medianLon = (lat) => MEDIAN_S[0] + ((lat - MEDIAN_S[1]) / (MEDIAN_N[1] - MEDIAN_S[1])) * (MEDIAN_N[0] - MEDIAN_S[0]);

// Per-side crops (lon/lat). West stops at Matsu's Dongyin group; east starts
// west of Penghu. Both share the latitude → y mapping (FRAME_LAT), so the two
// flanks hang on one vertical scale.
const SIDES = {
  west: { lon: [117.0, 120.65], lat: [23.35, 26.5] },
  east: { lon: [119.2, 122.15], lat: [21.85, 25.4] },
};
const FRAME_LAT = [21.85, 26.5];
// Fixed marker dots for island groups that are sub-pixel at masthead scale
// (standard inset practice). Kinmen and Penghu draw large enough as polygons.
const DOTS = {
  west: [[119.93, 26.16, "Matsu (Nangan / Beigan)"], [120.49, 26.37, "Matsu (Dongyin)"], [119.94, 25.97, "Matsu (Juguang)"], [119.45, 24.98, "Wuqiu"]],
  east: [[121.55, 22.05, "Lanyu"], [121.48, 22.66, "Green Island"]],
};

// ---- path re-simplification (Douglas-Peucker on the module's "M x y L x y …" strings)
function parsePath(d) {
  const nums = d.match(/-?\d+(?:\.\d+)?/g).map(Number);
  const pts = [];
  for (let i = 0; i + 1 < nums.length; i += 2) pts.push([nums[i], nums[i + 1]]);
  return { pts, closed: /Z\s*$/i.test(d) };
}
function perpDist([x, y], [ax, ay], [bx, by]) {
  const dx = bx - ax, dy = by - ay;
  if (!dx && !dy) return Math.hypot(x - ax, y - ay);
  const t = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)));
  return Math.hypot(x - (ax + t * dx), y - (ay + t * dy));
}
function dp(pts, eps) {
  if (pts.length < 3) return pts;
  let idx = 0, dmax = 0;
  for (let i = 1; i < pts.length - 1; i++) {
    const d = perpDist(pts[i], pts[0], pts[pts.length - 1]);
    if (d > dmax) { dmax = d; idx = i; }
  }
  if (dmax <= eps) return [pts[0], pts[pts.length - 1]];
  return dp(pts.slice(0, idx + 1), eps).slice(0, -1).concat(dp(pts.slice(idx), eps));
}
function simplify(d, eps) {
  const { pts, closed } = parsePath(d);
  const out = dp(pts, eps);
  if (closed && out.length < 4) return null;  // an island that collapsed — drop, the dot layer covers it
  return "M " + out.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join(" L ") + (closed ? " Z" : "");
}
// viewBox units (1 ≈ 2.2 km; the masthead draws ~0.42 px per unit). The Fujian
// ria coast is a saw-tooth of 10–15 km bays that read as a squiggle here, so
// the coast gets a ~20 km tolerance (keeps the Xiamen and Min estuaries) and
// inshore fragments shorter than ~30 km are dropped; islands keep their outlines.
const EPS_COAST = 9.0;
const EPS_ISLAND = 1.4;
const MIN_COAST_LEN = 15;
function pathLength(d) {
  const { pts } = parsePath(d);
  let L = 0;
  for (let i = 1; i < pts.length; i++) L += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
  return L;
}
const COAST = PRC_COAST_PATHS.filter((d) => pathLength(d) >= MIN_COAST_LEN)
  .map((d) => simplify(d, EPS_COAST)).filter(Boolean);
const ROC = TAIWAN_PATHS.map((d) => simplify(d, EPS_ISLAND)).filter(Boolean);

function clipPolygon(side) {
  const [latMin, latMax] = FRAME_LAT;
  const a = px(medianLon(latMax), latMax), b = px(medianLon(latMin - 1), latMin - 1);
  const edge = side === "west" ? -50 : SVG_W + 50;
  return `${edge},${a[1] - 50} ${a[0]},${a[1] - 50} ${b[0]},${b[1]} ${edge},${b[1]}`;
}

/**
 * One flank.
 *  height     the SHARED frame (lat 21.85–26.5) in px — sets the scale for both sides.
 *  boxHeight  the layout box the flank occupies (the nameplate's line height);
 *             the drawing is centred on it and overflows above/below, so the
 *             masthead doesn't grow to fit the map.
 */
export default function MastheadCoasts({ side = "west", height = 92, boxHeight = 40 }) {
  const crop = SIDES[side];
  const [x0, y0] = px(crop.lon[0], crop.lat[1]);
  const [x1, y1] = px(crop.lon[1], crop.lat[0]);
  const [, frameTop] = px(BBOX[0], FRAME_LAT[1]);
  const [, frameBottom] = px(BBOX[0], FRAME_LAT[0]);
  const scale = height / (frameBottom - frameTop);
  const w = (x1 - x0) * scale, h = (y1 - y0) * scale;
  const top = (boxHeight - height) / 2 + (y0 - frameTop) * scale;
  const clipId = `coast-clip-${side}`;
  const dotR = 2.1 / scale;
  return (
    <div aria-hidden="true" style={{ position: "relative", width: `${w}px`, height: `${boxHeight}px`, flexShrink: 0 }}>
      <svg viewBox={`${x0} ${y0} ${x1 - x0} ${y1 - y0}`} width={w} height={h}
           style={{ position: "absolute", top: `${top}px`, left: 0, overflow: "visible", display: "block" }}>
        <defs>
          <clipPath id={clipId}><polygon points={clipPolygon(side)} /></clipPath>
        </defs>
        <g clipPath={`url(#${clipId})`}>
          {side === "west" && COAST.map((d, i) => (
            <path key={`c${i}`} d={d} fill="none" stroke="var(--ink)" strokeOpacity="0.6"
                  strokeWidth="0.9" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
          ))}
          {ROC.map((d, i) => (
            <path key={`t${i}`} d={d} fill="var(--soft)" stroke="var(--ink)" strokeOpacity="0.6"
                  strokeWidth="0.9" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
          ))}
          {DOTS[side].map(([lon, lat, title]) => {
            const [cx, cy] = px(lon, lat);
            return <circle key={title} cx={cx} cy={cy} r={dotR} fill="var(--muted)"><title>{title}</title></circle>;
          })}
        </g>
      </svg>
    </div>
  );
}
