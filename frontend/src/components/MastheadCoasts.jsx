// The two sides of the strait flanking the nameplate (Ed's masthead idea,
// 2026-09-02), round 3: two EMBLEMS, not one map. Round 2 drew both flanks on
// one shared latitude scale, and a Fujian coast segment is not an icon at any
// smoothing. So each side is now its own filled silhouette at its own scale:
//
//   west — China's eastern seaboard from the Shandong peninsula down past the
//          Yangtze mouth, Fujian and the Pearl River to Leizhou and Hainan,
//          filled land that fades inland (a coastal band, so the source box's
//          straight cuts never show) with the coastline as the crisp edge;
//   east — Taiwan with the Penghu group, filled.
//
// Geometry: mastheadEmblems.js via `scripts/build_masthead_emblems.py`
// (Natural Earth 10m, box-clipped land + open coast runs, tolerances tuned
// there — retune and regenerate, never in JS). Colours are tokens (--soft
// fill, --ink stroke) so light and dark just work. Decorative — aria-hidden;
// the caller positions each flank absolutely and hides them on narrow
// viewports.
import React from "react";
import { MAINLAND, TAIWAN } from "./mastheadEmblems";

// Inland fade for the mainland: the coast is stroked wide and blurred in a
// luminance mask, so land within ~BAND viewBox-px of the sea is solid and
// then dissolves. In viewBox units (height 100 ≈ the flank's CSS height).
const BAND = 16;
const BLUR = 5;

const STROKE = { fill: "none", stroke: "var(--ink)", strokeOpacity: 0.6, strokeWidth: 0.9,
                 vectorEffect: "non-scaling-stroke", strokeLinejoin: "round" };

/** One flank. Fills its container's height; width follows from the emblem's aspect. */
export default function MastheadCoasts({ side = "west" }) {
  const emblem = side === "west" ? MAINLAND : TAIWAN;
  const style = { height: "100%", width: "auto", display: "block", overflow: "visible" };

  if (side === "east") {
    return (
      <svg aria-hidden="true" viewBox={emblem.viewBox} style={style}>
        {emblem.land.map((d, i) => <path key={i} d={d} {...STROKE} fill="var(--soft)" />)}
      </svg>
    );
  }

  const maskId = "masthead-band-west";
  return (
    <svg aria-hidden="true" viewBox={emblem.viewBox} style={style}>
      <defs>
        <filter id={`${maskId}-blur`} x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation={BLUR} />
        </filter>
        <mask id={maskId} maskUnits="userSpaceOnUse" x="-20" y="-20" width={emblem.w + 40} height={emblem.h + 40}>
          <g filter={`url(#${maskId}-blur)`}>
            {emblem.coast.map((d, i) => (
              <path key={i} d={d} fill="none" stroke="#fff" strokeWidth={BAND} strokeLinejoin="round" strokeLinecap="round" />
            ))}
          </g>
        </mask>
      </defs>
      <g mask={`url(#${maskId})`}>
        {emblem.land.map((d, i) => <path key={`l${i}`} d={d} fill="var(--soft)" />)}
        {emblem.coast.map((d, i) => <path key={`c${i}`} d={d} {...STROKE} />)}
      </g>
    </svg>
  );
}
