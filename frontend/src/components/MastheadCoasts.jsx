// The two sides of the strait flanking the nameplate (Ed's masthead idea,
// 2026-09-02): the mainland coast from Ningde down past Xiamen and Shantou to
// the Pearl River mouth, with Kinmen / Matsu / Wuqiu, to the WEST; Taiwan with
// Penghu / Lanyu / Green Island to the EAST; the nameplate sits where the
// strait is. One map, split along the Taiwan Strait Median Line, both flanks
// on ONE shared latitude scale (the full frame, lat 21–27), so Fujian rides
// north of Taiwan's bulk and the two sides stay geographically honest.
//
// Geometry: mastheadCoastPaths.js — Natural Earth via
// `scripts/build_taiwan_strait_map.py --masthead`, which uses a wider box than
// the Military map, tolerances tuned for masthead scale (~0.4 px per km), and
// exports PROJECTION so nothing is mirrored by hand. Paths are drawn as-is.
// Colours are tokens (--ink / --soft / --muted) so light and dark just work.
// Decorative — aria-hidden; the caller positions each flank absolutely and
// hides them on narrow viewports.
import React from "react";
import { TAIWAN_PATHS, PRC_COAST_PATHS, PROJECTION as P } from "./mastheadCoastPaths";

const px = (lon, lat) => [P.xOffset + (lon - P.bbox[0]) * P.pxPerDegLon, (P.bbox[3] - lat) * P.pxPerDegLat];

// Median Line (Davis Line) as MND publishes it; extended along its own slope
// so the split covers the whole frame.
const MEDIAN_N = [122.0, 27.0], MEDIAN_S = [117.85, 23.283];
const medianLon = (lat) => MEDIAN_S[0] + ((lat - MEDIAN_S[1]) / (MEDIAN_N[1] - MEDIAN_S[1])) * (MEDIAN_N[0] - MEDIAN_S[0]);

// Per-side longitude crops. Both use the FULL latitude range of the module, so
// the two SVGs have identical viewBox heights and `height: 100%` gives them
// one scale and one baseline. West stops at Matsu's Dongyin group; east
// starts west of Penghu.
const SIDES = {
  west: { lon: [P.bbox[0], 120.7] },
  east: { lon: [119.2, 122.2] },
};
// Fixed marker dots for island groups that are sub-pixel at masthead scale
// (standard inset practice). Kinmen and Penghu draw large enough as polygons.
const DOTS = {
  west: [[119.93, 26.16, "Matsu (Nangan / Beigan)"], [120.49, 26.37, "Matsu (Dongyin)"], [119.94, 25.97, "Matsu (Juguang)"], [119.45, 24.98, "Wuqiu"]],
  east: [[121.55, 22.05, "Lanyu"], [121.48, 22.66, "Green Island"]],
};

function clipPolygon(side) {
  const [latMin, latMax] = [P.bbox[1] - 1, P.bbox[3] + 1];
  const a = px(medianLon(latMax), latMax), b = px(medianLon(latMin), latMin);
  const edge = side === "west" ? -100 : P.w + 100;
  return `${edge},${a[1]} ${a[0]},${a[1]} ${b[0]},${b[1]} ${edge},${b[1]}`;
}

/** One flank. Fills its container's height; width follows from the crop's aspect. */
export default function MastheadCoasts({ side = "west" }) {
  const [x0, x1] = SIDES[side].lon.map((lon) => px(lon, P.bbox[3])[0]);
  const clipId = `coast-clip-${side}`;
  return (
    <svg aria-hidden="true" viewBox={`${x0.toFixed(1)} 0 ${(x1 - x0).toFixed(1)} ${P.h}`}
         style={{ height: "100%", width: "auto", display: "block", overflow: "visible" }}>
      <defs>
        <clipPath id={clipId}><polygon points={clipPolygon(side)} /></clipPath>
      </defs>
      <g clipPath={`url(#${clipId})`}>
        {side === "west" && PRC_COAST_PATHS.map((d, i) => (
          <path key={`c${i}`} d={d} fill="none" stroke="var(--ink)" strokeOpacity="0.6"
                strokeWidth="0.9" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        ))}
        {TAIWAN_PATHS.map((d, i) => (
          <path key={`t${i}`} d={d} fill="var(--soft)" stroke="var(--ink)" strokeOpacity="0.6"
                strokeWidth="0.9" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        ))}
        {DOTS[side].map(([lon, lat, title]) => {
          const [cx, cy] = px(lon, lat);
          return <circle key={title} cx={cx} cy={cy} r="5" fill="var(--muted)"><title>{title}</title></circle>;
        })}
      </g>
    </svg>
  );
}
