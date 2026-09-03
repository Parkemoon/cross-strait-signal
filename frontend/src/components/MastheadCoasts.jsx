// The two sides of the strait flanking the nameplate (Ed's masthead idea,
// 2026-09-02), round 3: two EMBLEMS, not one map. Round 2 drew both flanks on
// one shared latitude scale, and a Fujian coast segment is not an icon at any
// smoothing. So each side is its own filled silhouette at its own scale:
//
//   west — China's eastern seaboard from the Shandong peninsula down past the
//          Yangtze mouth, Fujian and the Pearl River to Leizhou and Hainan,
//          filled land that fades inland (a coastal band, so the source box's
//          straight cuts never show) with the coastline as the crisp edge;
//   east — Taiwan with the Penghu group, filled.
//
// Over each silhouette sits its flag as a SOFT WASH (Ed, 2026-09-03 — "the
// actual flag, like the Wikipedia flag map, but a soft gradient rather than a
// hard fill"): the PRC star group over the Jiangsu coast; Taiwan the flag-map
// way — the island's north is the blue field carrying the whole sun, the
// south is red, soft blend between. The wash fades from the north-west
// corner to the south-east so the sun and the stars carry the identity and
// the rest dissolves back into the paper fill underneath. Flag geometry is
// the flags' own (public-domain Commons SVGs — sun and stars exact); flag
// colours are literal because they are the flags', not tokens.
//
// Geometry: mastheadEmblems.js via `scripts/build_masthead_emblems.py`
// (Natural Earth 10m, box-clipped land + open coast runs, tolerances tuned
// there — retune and regenerate, never in JS). Silhouette colours are tokens
// (--soft fill, --ink stroke) so light and dark just work. Decorative —
// aria-hidden; the caller positions each flank absolutely and hides them on
// narrow viewports.
import React from "react";
import { MAINLAND, TAIWAN } from "./mastheadEmblems";

// Inland fade for the mainland: the coast is stroked wide and blurred in a
// luminance mask, so land within ~BAND viewBox-px of the sea is solid and
// then dissolves. In viewBox units (height 100 ≈ the flank's CSS height).
// Wide enough that the big star sits in the solid band.
const BAND = 24;
const BLUR = 6;

// Flag wash: opacity at the north-west corner → at the south-east corner.
const WASH_NW = 0.7;
const WASH_SE = 0.12;

// PRC star group: big star centre as fractions of the mainland viewBox, and
// its outer radius in viewBox units (the flag's big star has r=90 at 900×600).
const PRC_STAR = { x: 0.49, y: 0.21, r: 7.5 };

// Taiwan split: blue down to SPLIT of the island's height, blending into red
// over SOFT of it; sun ray-tip radius as a fraction of the island's width.
const TW_SPLIT = 0.36;
const TW_SOFT = 0.10;
const TW_SUN_R = 0.27;

const STROKE = { fill: "none", stroke: "var(--ink)", strokeOpacity: 0.6, strokeWidth: 0.9,
                 vectorEffect: "non-scaling-stroke", strokeLinejoin: "round" };

// Main-island bbox + mean x of the northern section (sun centre), from the
// path string once at module load.
const TW_ISLAND = (() => {
  const pts = [...TAIWAN.land[0].matchAll(/[ML] ([\d.]+) ([\d.]+)/g)].map((m) => [+m[1], +m[2]]);
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const north = pts.filter(([, y]) => y < y0 + (y1 - y0) * TW_SPLIT).map(([x]) => x);
  return { x0, y0, w: x1 - x0, h: y1 - y0, northX: north.reduce((a, b) => a + b, 0) / north.length };
})();

/** NW→SE opacity ramp over an emblem's viewBox, as a luminance mask. */
function WashMask({ id, emblem }) {
  return (
    <>
      <linearGradient id={`${id}-g`} gradientUnits="userSpaceOnUse" x1="0" y1="0" x2={emblem.w} y2={emblem.h}>
        <stop offset="0" stopColor="#fff" stopOpacity={WASH_NW} />
        <stop offset="1" stopColor="#fff" stopOpacity={WASH_SE} />
      </linearGradient>
      <mask id={id} maskUnits="userSpaceOnUse" x="0" y="0" width={emblem.w} height={emblem.h}>
        <rect width={emblem.w} height={emblem.h} fill={`url(#${id}-g)`} />
      </mask>
    </>
  );
}

/** The ROC sun: 12 rays + disc, from the flag's own geometry (r=15 about 30,20). */
function Sun({ cx, cy, r }) {
  const s = r / 15;
  return (
    <g transform={`translate(${(cx - 30 * s).toFixed(2)} ${(cy - 20 * s).toFixed(2)}) scale(${s.toFixed(4)})`}>
      <path id="roc-ray" d="M30 5l4 15-4 15-4-15zM15 20l15 4 15-4-15-4z" fill="#fff" />
      <use href="#roc-ray" transform="rotate(30,30,20)" />
      <use href="#roc-ray" transform="rotate(60,30,20)" />
      <circle cx="30" cy="20" r="8" fill="#fff" stroke="#000094" strokeWidth="1" />
    </g>
  );
}

/** The PRC star group, from the flag's own geometry (big star at 150,150 of 900×600). */
function Stars({ cx, cy, r }) {
  const s = r / 90;
  return (
    <g transform={`translate(${(cx - 150 * s).toFixed(2)} ${(cy - 150 * s).toFixed(2)}) scale(${s.toFixed(4)})`}>
      <g transform="matrix(3 0 0 3 150 150)">
        <path id="prc-star" d="m0-30 17.634 54.27-46.166-33.54h57.064l-46.166 33.54Z" fill="#FF0" />
      </g>
      <use href="#prc-star" transform="rotate(23.036 2.784 766.082)" />
      <use href="#prc-star" transform="rotate(45.87 38.201 485.396)" />
      <use href="#prc-star" transform="rotate(69.945 29.892 362.328)" />
      <use href="#prc-star" transform="rotate(20.66 -590.66 957.955)" />
    </g>
  );
}

/** One flank. Fills its container's height; width follows from the emblem's aspect. */
export default function MastheadCoasts({ side = "west" }) {
  const emblem = side === "west" ? MAINLAND : TAIWAN;
  const style = { height: "100%", width: "auto", display: "block", overflow: "visible" };

  if (side === "east") {
    const t = TW_ISLAND;
    const ya = t.y0 + t.h * (TW_SPLIT - TW_SOFT / 2), yb = t.y0 + t.h * (TW_SPLIT + TW_SOFT / 2);
    return (
      <svg aria-hidden="true" viewBox={emblem.viewBox} style={style}>
        <defs>
          <clipPath id="masthead-clip-east">{emblem.land.map((d, i) => <path key={i} d={d} />)}</clipPath>
          <linearGradient id="roc-split" gradientUnits="userSpaceOnUse" x1="0" y1={ya.toFixed(1)} x2="0" y2={yb.toFixed(1)}>
            <stop offset="0" stopColor="#000094" />
            <stop offset="1" stopColor="#fe0000" />
          </linearGradient>
          <WashMask id="masthead-wash-east" emblem={emblem} />
        </defs>
        {emblem.land.map((d, i) => <path key={i} d={d} fill="var(--soft)" />)}
        <g clipPath="url(#masthead-clip-east)" mask="url(#masthead-wash-east)">
          <rect x="-50" y="-50" width={emblem.w + 100} height={emblem.h + 100} fill="url(#roc-split)" />
          <Sun cx={t.northX} cy={t.y0 + t.h * TW_SPLIT * 0.5} r={t.w * TW_SUN_R} />
        </g>
        {emblem.land.map((d, i) => <path key={`s${i}`} d={d} {...STROKE} />)}
      </svg>
    );
  }

  return (
    <svg aria-hidden="true" viewBox={emblem.viewBox} style={style}>
      <defs>
        <filter id="masthead-band-blur" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation={BLUR} />
        </filter>
        <mask id="masthead-band-west" maskUnits="userSpaceOnUse" x="-20" y="-20" width={emblem.w + 40} height={emblem.h + 40}>
          <g filter="url(#masthead-band-blur)">
            {emblem.coast.map((d, i) => (
              <path key={i} d={d} fill="none" stroke="#fff" strokeWidth={BAND} strokeLinejoin="round" strokeLinecap="round" />
            ))}
          </g>
        </mask>
        <clipPath id="masthead-clip-west">{emblem.land.map((d, i) => <path key={i} d={d} />)}</clipPath>
        <WashMask id="masthead-wash-west" emblem={emblem} />
      </defs>
      <g mask="url(#masthead-band-west)">
        {emblem.land.map((d, i) => <path key={`l${i}`} d={d} fill="var(--soft)" />)}
        <g clipPath="url(#masthead-clip-west)" mask="url(#masthead-wash-west)">
          <rect x="-50" y="-50" width={emblem.w + 100} height={emblem.h + 100} fill="#EE1C25" />
          <Stars cx={emblem.w * PRC_STAR.x} cy={emblem.h * PRC_STAR.y} r={PRC_STAR.r} />
        </g>
        {emblem.coast.map((d, i) => <path key={`c${i}`} d={d} {...STROKE} />)}
      </g>
    </svg>
  );
}
