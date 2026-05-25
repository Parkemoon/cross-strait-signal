import { useEffect, useMemo, useState } from "react";
import {
  Bar, Line, ComposedChart, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, AreaChart, Area,
} from "recharts";
import {
  fetchMilitaryIncursions,
  fetchMilitarySummary,
  fetchMilitaryZones,
  fetchMilitaryExercises,
  fetchMilitaryExerciseCandidates,
  dismissMilitaryExercise,
} from "../api";
import { READ_ONLY } from "../readOnly";
import { TAIWAN_PATHS, PRC_COAST_PATHS, MEDIAN_LINE } from "./taiwanStraitMap";
import ExerciseMap, { PERFORMER_COLOUR, PERFORMER_LABEL } from "./ExerciseMap";
import ExerciseReviewQueue from "./ExerciseReviewQueue";
import ExerciseEditModal from "./ExerciseEditModal";

// Purple is the project's "hostile" colour (locked). PLA incursions are the
// prototypical hostile cross-strait act, so the whole tab leans purple.
const HOSTILE = "#7c3aed";
const HOSTILE_DIM = "rgba(124, 58, 237, 0.20)";

const MONTH_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

// "2026-05-22" → "May 22"
function fmtMonthDay(iso) {
  if (!iso) return "";
  const [, m, d] = iso.split("-");
  return `${MONTH_ABBR[Number(m) - 1]} ${Number(d)}`;
}

function SectionHeader({ children, right }) {
  return (
    <div style={{ marginBottom: "16px", marginTop: "28px" }}>
      <div style={{ height: "2px", background: "var(--border-color)", marginBottom: "9px" }} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: "11px",
          fontWeight: 600,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: "var(--text-primary)",
        }}>
          {children}
        </span>
        {right && (
          <span style={{
            fontFamily: "var(--font-mono)",
            fontSize: "10px",
            color: "var(--text-muted)",
          }}>
            {right}
          </span>
        )}
      </div>
      <div style={{ height: "1px", background: "var(--border-color)", marginTop: "9px" }} />
    </div>
  );
}

function KPICard({ value, label, sublabel, chip }) {
  return (
    <div style={{
      padding: "14px 16px",
      border: "1px solid var(--border-color)",
      background: "var(--bg-card)",
      minWidth: 0,
    }}>
      <div style={{
        fontFamily: "var(--font-mono)",
        fontSize: "10px",
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        color: "var(--text-muted)",
        marginBottom: "6px",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: "8px",
      }}>
        <span>{label}</span>
        {chip}
      </div>
      <div style={{
        fontFamily: "var(--font-display)",
        fontSize: "26px",
        fontWeight: 500,
        color: "var(--text-primary)",
        lineHeight: 1.1,
      }}>{value}</div>
      {sublabel && (
        <div style={{
          fontFamily: "var(--font-body)",
          fontSize: "11px",
          color: "var(--text-secondary)",
          marginTop: "4px",
        }}>{sublabel}</div>
      )}
    </div>
  );
}

function YoYChip({ pct }) {
  if (pct === null || pct === undefined) return null;
  // YoY decrease in PLA activity is "less hostile" → use the project's
  // cooperative-amber; increase → hostile-purple. This mirrors the
  // sentiment palette so the chip semantics match the rest of the app.
  const positive = pct >= 0;
  const colour = positive ? HOSTILE : "#b8860b";
  const bg     = positive ? "rgba(124,58,237,0.12)" : "rgba(184,134,11,0.14)";
  return (
    <span style={{
      fontFamily: "var(--font-mono)",
      fontSize: "9.5px",
      letterSpacing: "0.04em",
      color: colour,
      background: bg,
      border: `1px solid ${colour}55`,
      padding: "1px 5px",
      whiteSpace: "nowrap",
    }}>
      {positive ? "▲" : "▼"} {Math.abs(pct).toFixed(1)}% YoY
    </span>
  );
}

// 7-day trailing average for a given date — fills nulls with no contribution.
function rolling7(rows, idx, key) {
  const slice = rows.slice(Math.max(0, idx - 6), idx + 1)
                    .map((r) => r[key])
                    .filter((v) => v !== null && v !== undefined);
  if (slice.length === 0) return null;
  return slice.reduce((a, b) => a + b, 0) / slice.length;
}

function DailyBarsChart({ rows }) {
  const enriched = useMemo(() => rows.map((r, i) => ({
    date: r.date,
    intruded: r.aircraft_intruded,
    rolling: rolling7(rows, i, "aircraft_intruded"),
  })), [rows]);

  return (
    <div style={{ height: "260px" }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={enriched} margin={{ top: 12, right: 12, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="var(--border-color)" />
          <XAxis
            dataKey="date"
            tick={{ fontFamily: "var(--font-mono)", fontSize: 10, fill: "var(--text-muted)" }}
            stroke="var(--border-color)"
            tickFormatter={fmtMonthDay}
            interval="preserveStartEnd"
            minTickGap={42}
          />
          <YAxis
            tick={{ fontFamily: "var(--font-mono)", fontSize: 10, fill: "var(--text-muted)" }}
            stroke="var(--border-color)"
          />
          <Tooltip
            contentStyle={{
              background: "var(--bg-primary)",
              border: "1px solid var(--border-color)",
              fontFamily: "var(--font-mono)",
              fontSize: "11px",
            }}
            labelFormatter={(d) => fmtMonthDay(d)}
            formatter={(v, key) => {
              if (v === null || v === undefined) return ["—", key];
              const label = key === "rolling" ? "7-day avg" : "Aircraft intruded";
              const display = key === "rolling" ? v.toFixed(1) : v;
              return [display, label];
            }}
          />
          <Bar dataKey="intruded" fill={HOSTILE} maxBarSize={9} />
          <Line type="monotone" dataKey="rolling" stroke="var(--text-primary)"
                strokeWidth={1.5} dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

// Vessel + coast-guard sparkline — only renders the MND-era window because
// PLATracker never published vessel counts.
function VesselSparkline({ rows }) {
  const mndOnly = useMemo(
    () => rows.filter((r) => r.vessels_total !== null && r.vessels_total !== undefined),
    [rows],
  );
  if (mndOnly.length === 0) {
    return (
      <p style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-muted)" }}>
        No vessel reports in the loaded window.
      </p>
    );
  }
  return (
    <div style={{ height: "150px", marginTop: "4px" }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={mndOnly} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="var(--border-color)" />
          <XAxis
            dataKey="date"
            tick={{ fontFamily: "var(--font-mono)", fontSize: 10, fill: "var(--text-muted)" }}
            stroke="var(--border-color)"
            tickFormatter={fmtMonthDay}
            interval="preserveStartEnd"
            minTickGap={42}
          />
          <YAxis
            tick={{ fontFamily: "var(--font-mono)", fontSize: 10, fill: "var(--text-muted)" }}
            stroke="var(--border-color)"
          />
          <Tooltip
            contentStyle={{
              background: "var(--bg-primary)",
              border: "1px solid var(--border-color)",
              fontFamily: "var(--font-mono)",
              fontSize: "11px",
            }}
            labelFormatter={fmtMonthDay}
            formatter={(v, key) => [
              v === null || v === undefined ? "—" : v,
              key === "vessels_total" ? "PLA vessels" : "Coast guard",
            ]}
          />
          <Area
            type="monotone"
            dataKey="vessels_total"
            stroke={HOSTILE}
            fill={HOSTILE_DIM}
            strokeWidth={1.5}
          />
          <Line
            type="monotone"
            dataKey="coast_guard_total"
            stroke="var(--text-primary)"
            strokeWidth={1.2}
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// Schematic ADIZ — stylised vertical Taiwan with the five sectors at their
// approximate compass positions. Sector colour intensity scales with the
// share of the last 30 days that sector saw any incursion.
function ADIZSchematic({ rows, zoneLabels }) {
  const window30 = rows.slice(-30);
  const totals = { N: 0, C: 0, SW: 0, SE: 0, E: 0 };
  let withZoneData = 0;
  for (const r of window30) {
    if (!r.aircraft_zones) continue;
    withZoneData += 1;
    for (const code of r.aircraft_zones.split(",")) {
      const k = code.trim();
      if (k in totals) totals[k] += 1;
    }
  }
  const maxTouch = Math.max(1, ...Object.values(totals));

  // Sector pill positions, placed around the real Taiwan + PRC coast paths
  // (generated by scripts/build_taiwan_strait_map.py — viewBox 0..320, 0..260).
  // Coordinates are an analyst-pleasing approximation of where each named
  // MND sector lies relative to the island; the side panel below carries
  // the precise day counts.
  const sectors = [
    { code: "N",  cx: 210, cy: 24,  label: "North"     },
    { code: "C",  cx: 110, cy: 110, label: "Central"   },
    { code: "E",  cx: 285, cy: 130, label: "East"      },
    { code: "SW", cx: 130, cy: 240, label: "Southwest" },
    { code: "SE", cx: 250, cy: 240, label: "Southeast" },
  ];

  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "minmax(300px, 380px) 1fr",
      gap: "20px",
      alignItems: "start",
    }}>
      <svg viewBox="0 0 320 260" style={{ width: "100%", height: "auto" }}>
        {/* Strait water fill — subtle, so coast and Taiwan read clearly */}
        <rect x="0" y="0" width="320" height="260" fill="var(--bg-card)" opacity="0.35" />
        <text x="10" y="14" fontFamily="var(--font-mono)" fontSize="9"
              fill="var(--text-muted)" letterSpacing="0.08em">PRC</text>
        <text x="295" y="14" fontFamily="var(--font-mono)" fontSize="9"
              fill="var(--text-muted)" letterSpacing="0.08em">PAC</text>

        {/* PRC mainland coast — open polylines (stroke only, no fill).
            Drawn under the sector pills so the pills overlay cleanly. */}
        {PRC_COAST_PATHS.map((d, i) => (
          <path key={`prc-${i}`} d={d} fill="none"
                stroke="var(--text-secondary)" strokeOpacity="0.55"
                strokeWidth="0.8" strokeLinejoin="round" />
        ))}

        {/* Taiwan Strait Median Line — dashed; PLA crossings of this line
            are the headline "intruded" count in the daily MND release. */}
        <line
          x1={MEDIAN_LINE.x1} y1={MEDIAN_LINE.y1}
          x2={MEDIAN_LINE.x2} y2={MEDIAN_LINE.y2}
          stroke={HOSTILE} strokeOpacity="0.55"
          strokeWidth="0.8" strokeDasharray="3 2"
        />
        <text
          x={(MEDIAN_LINE.x1 + MEDIAN_LINE.x2) / 2 + 4}
          y={(MEDIAN_LINE.y1 + MEDIAN_LINE.y2) / 2 - 4}
          fontFamily="var(--font-mono)" fontSize="8"
          fill={HOSTILE} fillOpacity="0.75"
          letterSpacing="0.06em">
          MEDIAN LINE
        </text>

        {/* Taiwan + outlying islands (Penghu, Matsu, Kinmen, Lanyu,
            Green Island) — closed shapes */}
        {TAIWAN_PATHS.map((d, i) => (
          <path key={`tw-${i}`} d={d}
                fill="var(--bg-primary)"
                stroke="var(--text-primary)" strokeWidth="1.1"
                strokeLinejoin="round" />
        ))}

        {/* Sector pills */}
        {sectors.map((s) => {
          const days = totals[s.code];
          const intensity = days / maxTouch;
          const fill = days > 0
            ? `rgba(124, 58, 237, ${0.20 + intensity * 0.65})`
            : "var(--bg-card)";
          const stroke = days > 0 ? HOSTILE : "var(--border-color)";
          return (
            <g key={s.code}>
              <rect
                x={s.cx - 22} y={s.cy - 13} width="44" height="26"
                fill={fill} stroke={stroke} strokeWidth="1"
              />
              <text x={s.cx} y={s.cy - 1} textAnchor="middle"
                    fontFamily="var(--font-mono)" fontSize="10"
                    fontWeight="600"
                    fill="var(--text-primary)" letterSpacing="0.06em">
                {s.code}
              </text>
              <text x={s.cx} y={s.cy + 9} textAnchor="middle"
                    fontFamily="var(--font-mono)" fontSize="8"
                    fill="var(--text-secondary)">
                {days}d
              </text>
            </g>
          );
        })}
      </svg>
      <div style={{
        fontFamily: "var(--font-mono)",
        fontSize: "11px",
        color: "var(--text-secondary)",
        lineHeight: 1.55,
      }}>
        <div style={{
          fontFamily: "var(--font-mono)",
          fontSize: "10px",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "var(--text-muted)",
          marginBottom: "10px",
        }}>
          Last 30 days · {withZoneData} reporting days
        </div>
        {Object.entries(totals)
          .sort((a, b) => b[1] - a[1])
          .map(([code, days]) => {
            const label = (zoneLabels || []).find((z) => z.code === code)?.label || code;
            return (
              <div key={code} style={{
                display: "flex", justifyContent: "space-between",
                padding: "3px 0", borderBottom: "1px dotted var(--border-color)",
              }}>
                <span>{label}</span>
                <span style={{
                  color: days > 0 ? "var(--text-primary)" : "var(--text-muted)",
                }}>{days} day{days === 1 ? "" : "s"}</span>
              </div>
            );
          })}
      </div>
    </div>
  );
}

// 365-day calendar heatmap. Columns = ISO week, rows = day-of-week.
// Intensity scales with aircraft_intruded; days with no row at all are blank.
function Heatmap({ rows }) {
  const byDate = useMemo(() => {
    const m = new Map();
    for (const r of rows) m.set(r.date, r);
    return m;
  }, [rows]);

  const end = new Date();
  end.setHours(0, 0, 0, 0);
  const start = new Date(end);
  start.setDate(start.getDate() - 364);

  // Align the grid so the first column starts on the Sunday <= start.
  const gridStart = new Date(start);
  gridStart.setDate(gridStart.getDate() - gridStart.getDay());

  const cells = [];
  for (let d = new Date(gridStart); d <= end; d.setDate(d.getDate() + 1)) {
    cells.push(new Date(d));
  }

  const values = rows
    .map((r) => r.aircraft_intruded)
    .filter((v) => v !== null && v !== undefined && v > 0);
  const p95 = values.length > 0
    ? values.slice().sort((a, b) => a - b)[Math.floor(values.length * 0.95)]
    : 1;

  const cellSize = 11;
  const gap = 2;
  const cols = Math.ceil(cells.length / 7);
  const width = cols * (cellSize + gap);
  const height = 7 * (cellSize + gap) + 16;

  function intensity(v) {
    if (v === null || v === undefined) return null;
    if (v === 0) return 0;
    return Math.min(1, v / p95);
  }

  function fillFor(v) {
    const i = intensity(v);
    if (i === null) return "transparent";
    if (i === 0) return "var(--bg-card)";
    return `rgba(124, 58, 237, ${0.18 + i * 0.7})`;
  }

  const monthLabels = [];
  let lastMonth = -1;
  cells.forEach((d, i) => {
    if (d.getDay() === 0 && d.getMonth() !== lastMonth) {
      lastMonth = d.getMonth();
      monthLabels.push({
        x: Math.floor(i / 7) * (cellSize + gap),
        label: MONTH_ABBR[d.getMonth()],
      });
    }
  });

  return (
    <div style={{ overflowX: "auto" }}>
      <svg width={width} height={height} style={{ display: "block" }}>
        {monthLabels.map((m, i) => (
          <text key={i} x={m.x} y="10" fontFamily="var(--font-mono)" fontSize="9"
                fill="var(--text-muted)">
            {m.label}
          </text>
        ))}
        {cells.map((d, i) => {
          if (d < start || d > end) return null;
          const iso = d.toISOString().slice(0, 10);
          const row = byDate.get(iso);
          const v = row?.aircraft_intruded;
          const col = Math.floor(i / 7);
          const r = i % 7;
          return (
            <rect
              key={iso}
              x={col * (cellSize + gap)}
              y={r * (cellSize + gap) + 16}
              width={cellSize}
              height={cellSize}
              fill={fillFor(v)}
              stroke={row ? "transparent" : "var(--border-color)"}
              strokeOpacity="0.4"
              strokeDasharray={row ? "" : "1 1"}
            >
              <title>
                {iso}{row
                  ? ` · ${v ?? 0} intruded${row.aircraft_total ? ` / ${row.aircraft_total} total` : ""}`
                  : " · no report"}
              </title>
            </rect>
          );
        })}
      </svg>
      <div style={{
        display: "flex", alignItems: "center", gap: "8px",
        marginTop: "10px",
        fontFamily: "var(--font-mono)", fontSize: "10px",
        color: "var(--text-muted)",
      }}>
        <span>Less</span>
        {[0, 0.25, 0.5, 0.75, 1].map((i) => (
          <span key={i} style={{
            width: "12px", height: "12px",
            background: i === 0 ? "var(--bg-card)" : `rgba(124, 58, 237, ${0.18 + i * 0.7})`,
            border: i === 0 ? "1px solid var(--border-color)" : "none",
            display: "inline-block",
          }} />
        ))}
        <span>More</span>
        <span style={{ marginLeft: "16px" }}>
          Dashed = no MND/PLATracker report. Scale capped at p95 of non-zero days.
        </span>
      </div>
    </div>
  );
}

const DATE_RANGES = [
  { key: 30,  label: "30d" },
  { key: 90,  label: "90d" },
  { key: 365, label: "1y"  },
  { key: 1000, label: "All" },
];

function PerformerPill({ code, active, count, onToggle }) {
  const colour = PERFORMER_COLOUR[code];
  return (
    <button
      onClick={() => onToggle(code)}
      style={{
        padding: "3px 9px",
        fontFamily: "var(--font-mono)",
        fontSize: "10px",
        letterSpacing: "0.06em",
        border: `1px solid ${active ? colour : "var(--border-color)"}`,
        background: active ? `${colour}22` : "transparent",
        color: active ? colour : "var(--text-muted)",
        cursor: "pointer",
      }}
    >
      <span style={{ display: "inline-block", width: "8px", height: "8px",
                     background: colour, marginRight: "6px", verticalAlign: "middle" }} />
      {PERFORMER_LABEL[code]}{count !== undefined ? ` (${count})` : ""}
    </button>
  );
}

function ExerciseFilters({ filters, setFilters, counts, pendingCount, onOpenReview }) {
  const togglePerformer = (code) => {
    const next = new Set(filters.performers);
    if (next.has(code)) next.delete(code); else next.add(code);
    setFilters({ ...filters, performers: next });
  };
  return (
    <div style={{
      display: "flex", flexWrap: "wrap", alignItems: "center",
      gap: "6px", marginBottom: "12px",
    }}>
      {Object.keys(PERFORMER_LABEL).map((p) => (
        <PerformerPill key={p} code={p}
                       active={filters.performers.has(p)}
                       count={counts?.[p]}
                       onToggle={togglePerformer} />
      ))}
      <div style={{ flex: 1 }} />
      <div style={{ display: "flex", border: "1px solid var(--border-color)" }}>
        {DATE_RANGES.map((r) => (
          <button key={r.key}
                  onClick={() => setFilters({ ...filters, days: r.key })}
                  style={{
                    padding: "3px 9px",
                    fontFamily: "var(--font-mono)",
                    fontSize: "10px",
                    background: filters.days === r.key ? "var(--text-primary)" : "transparent",
                    color: filters.days === r.key ? "var(--bg-primary)" : "var(--text-secondary)",
                    border: "none",
                    cursor: "pointer",
                  }}>
            {r.label}
          </button>
        ))}
      </div>
      {!READ_ONLY && onOpenReview && (
        <button onClick={onOpenReview}
                title={`${pendingCount} pending`}
                style={{
                  padding: "3px 9px",
                  fontFamily: "var(--font-mono)",
                  fontSize: "10px",
                  letterSpacing: "0.06em",
                  border: `1px solid ${pendingCount > 0 ? "#d4a94a" : "var(--border-color)"}`,
                  background: pendingCount > 0 ? "rgba(212,169,74,0.12)" : "transparent",
                  color: pendingCount > 0 ? "#d4a94a" : "var(--text-muted)",
                  cursor: "pointer",
                }}>
          ✎ Review{pendingCount > 0 ? ` (${pendingCount})` : ""}
        </button>
      )}
    </div>
  );
}

// Small square icon button used by the per-row admin controls below.
function RowIconButton({ title, onClick, colour, children }) {
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      title={title}
      style={{
        background: "transparent",
        border: "1px solid var(--border-color)",
        color: colour || "var(--text-muted)",
        cursor: "pointer",
        padding: "1px 6px",
        fontSize: "11px",
        lineHeight: 1.2,
        fontFamily: "var(--font-mono)",
      }}
    >
      {children}
    </button>
  );
}

function ExerciseList({ rows, selectedId, onSelect, onEdit, onQuickDismiss }) {
  if (!rows || rows.length === 0) {
    return (
      <div style={{
        padding: "20px",
        fontFamily: "var(--font-mono)", fontSize: "11px",
        color: "var(--text-muted)", textAlign: "center",
      }}>
        No approved exercises in this window.
      </div>
    );
  }
  return (
    <div style={{
      maxHeight: "460px",
      overflowY: "auto",
      border: "1px solid var(--border-color)",
      background: "var(--bg-card)",
    }}>
      {rows.map((ex) => {
        const colour = PERFORMER_COLOUR[ex.performer] || "#666";
        const hasGeo = typeof ex.latitude === "number" && typeof ex.longitude === "number";
        const displayName = ex.name_en || (ex.name_zh
          ? `${ex.name_zh}`
          : `${PERFORMER_LABEL[ex.performer]} ${(ex.exercise_kind || "other").replace("_", " ")}`);
        const isSelected = ex.id === selectedId;
        return (
          <div
            key={ex.id}
            onClick={hasGeo ? () => onSelect(ex.id) : undefined}
            title={hasGeo ? "Click to centre map on this exercise" : "No location — not on map"}
            style={{
              padding: "8px 12px",
              borderLeft: isSelected ? `3px solid ${colour}` : "3px solid transparent",
              borderBottom: "1px solid var(--border-color)",
              background: isSelected ? `${colour}11` : "transparent",
              cursor: hasGeo ? "pointer" : "default",
              fontFamily: "var(--font-mono)",
              fontSize: "11px",
            }}>
            <div style={{ display: "flex", justifyContent: "space-between",
                          alignItems: "baseline", gap: "8px" }}>
              <span style={{
                fontFamily: "var(--font-display, serif)",
                fontSize: "13px",
                color: "var(--text-primary)",
              }}>{displayName}</span>
              <span style={{ color: colour, fontWeight: 700, letterSpacing: "0.06em",
                             fontSize: "9px", textTransform: "uppercase",
                             whiteSpace: "nowrap" }}>
                {PERFORMER_LABEL[ex.performer]}
              </span>
            </div>
            <div style={{ color: "var(--text-muted)", marginTop: "2px",
                          display: "flex", justifyContent: "space-between" }}>
              <span>
                {ex.start_date || "—"}
                {ex.end_date && ex.end_date !== ex.start_date ? ` → ${ex.end_date}` : ""}
              </span>
              <span style={{ fontStyle: hasGeo ? "normal" : "italic",
                             color: hasGeo ? "var(--text-secondary)" : "var(--text-muted)" }}>
                {ex.location_label || (hasGeo ? "" : "(no location)")}
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                          marginTop: "4px", gap: "8px" }}>
              {ex.article?.url ? (
                <a href={ex.article.url} target="_blank" rel="noreferrer"
                   onClick={(e) => e.stopPropagation()}
                   style={{ color: "var(--text-muted)",
                            fontSize: "9.5px", letterSpacing: "0.05em",
                            textTransform: "uppercase", textDecoration: "underline" }}>
                  via {ex.article.source_name}
                </a>
              ) : <span />}
              {!READ_ONLY && onEdit && (
                <span style={{ display: "flex", gap: "4px" }}>
                  <RowIconButton title="Edit this exercise"
                                 onClick={() => onEdit(ex)}>
                    ✎
                  </RowIconButton>
                  <RowIconButton title="Dismiss this exercise"
                                 colour="var(--accent-red, #dc2626)"
                                 onClick={() => onQuickDismiss(ex)}>
                    ✕
                  </RowIconButton>
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function MilitaryTab() {
  const [summary, setSummary] = useState(null);
  const [daily, setDaily] = useState(null);
  const [zones, setZones] = useState(null);
  const [error, setError] = useState(false);

  // Exercise tracker state — independent fetches, separate filters.
  const [exercises, setExercises] = useState(null);
  const [pendingCount, setPendingCount] = useState(0);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [editingExercise, setEditingExercise] = useState(null);
  const [selectedExerciseId, setSelectedExerciseId] = useState(null);
  const [exFilters, setExFilters] = useState({
    days: 90,
    performers: new Set(["PRC", "ROC", "US", "JP", "MULTI"]),
  });

  useEffect(() => {
    Promise.all([
      fetchMilitarySummary(),
      fetchMilitaryIncursions({ days: 365 }),
      fetchMilitaryZones(),
    ])
      .then(([s, d, z]) => {
        setSummary(s);
        setDaily(d);
        setZones(z?.zones || []);
      })
      .catch(() => setError(true));
  }, []);

  // Re-fetch approved exercises when the date window changes; performer
  // filter is applied client-side from this row set so toggling pills
  // is instant.
  useEffect(() => {
    fetchMilitaryExercises({ days: exFilters.days })
      .then((r) => setExercises(r.rows || []))
      .catch(() => setExercises([]));
  }, [exFilters.days]);

  // Pending-count badge — admin build only.
  const loadPendingCount = () => {
    if (READ_ONLY) return;
    fetchMilitaryExerciseCandidates()
      .then((r) => setPendingCount(r.total_pending || 0))
      .catch(() => setPendingCount(0));
  };
  useEffect(() => { loadPendingCount(); }, []);

  // Apply an in-place row replacement after a successful PATCH so the list
  // and map update without a full re-fetch round-trip. Server returns the
  // post-update row in the same shape /exercises serves.
  const handleExerciseSaved = (updated) => {
    setExercises((prev) => (prev || []).map((e) => (e.id === updated.id ? updated : e)));
    setEditingExercise(null);
  };

  // Drop the row locally after dismiss — backend will 404 it from /exercises
  // on next fetch anyway; this just avoids the round-trip.
  const handleExerciseDismissed = (id) => {
    setExercises((prev) => (prev || []).filter((e) => e.id !== id));
    if (selectedExerciseId === id) setSelectedExerciseId(null);
    setEditingExercise(null);
  };

  // One-click dismiss from the list — matches the no-confirm pattern of
  // ArticleCard's Dismiss and the candidate review queue's Dismiss.
  const handleQuickDismiss = async (ex) => {
    try {
      await dismissMilitaryExercise(ex.id);
      handleExerciseDismissed(ex.id);
    } catch (e) {
      // eslint-disable-next-line no-alert
      window.alert(`Dismiss failed: ${e.message || e}`);
    }
  };

  // Client-side performer filter + per-performer counts (for the pill labels).
  const filteredExercises = useMemo(() => {
    if (!exercises) return [];
    return exercises.filter((e) => exFilters.performers.has(e.performer));
  }, [exercises, exFilters.performers]);
  const performerCounts = useMemo(() => {
    const c = { PRC: 0, ROC: 0, US: 0, JP: 0, MULTI: 0 };
    for (const e of exercises || []) c[e.performer] = (c[e.performer] || 0) + 1;
    return c;
  }, [exercises]);

  if (error) {
    return (
      <main style={{ padding: "28px 32px" }}>
        <p style={{ color: "var(--accent-red)", fontFamily: "var(--font-mono)", fontSize: "13px", padding: "40px 0" }}>
          Couldn't load military activity.
        </p>
      </main>
    );
  }
  if (!summary || !daily) {
    return (
      <main style={{ padding: "28px 32px" }}>
        <p style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: "13px", padding: "40px 0" }}>
          Loading PLA activity…
        </p>
      </main>
    );
  }

  const rows = daily.rows || [];
  const last90 = rows.slice(-90);

  return (
    <main style={{ padding: "28px 32px", minWidth: 0 }}>
      <SectionHeader right={summary.latest_date ? `Latest report ${summary.latest_date}` : null}>
        PLA Activity Around Taiwan
      </SectionHeader>

      <p style={{
        fontFamily: "var(--font-body)",
        fontSize: "13px",
        color: "var(--text-secondary)",
        lineHeight: 1.55,
        margin: "0 0 18px",
      }}>
        Daily PLA aircraft and vessel activity as reported by Taiwan's Ministry of National Defence.
        Live from <em>mnd.gov.tw</em> back to {rows[Math.max(0, rows.length - 1)] && rows.find((r) => r.source === "mnd")?.date};
        historical incursion counts extended with the public PLATracker archive.
      </p>

      {/* KPI strip */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
        gap: "12px",
      }}>
        <KPICard
          label="Today"
          value={summary.today?.aircraft_intruded ?? "—"}
          sublabel={summary.today
            ? `${summary.today.aircraft_total ?? "?"} sorties · ${summary.today.vessels_total ?? 0} vessels`
            : "no report yet"}
        />
        <KPICard
          label="7-day avg"
          value={summary.avg_7d_intruded ?? "—"}
          sublabel="aircraft intruded / day"
        />
        <KPICard
          label="30-day avg"
          value={summary.avg_30d_intruded ?? "—"}
          sublabel={summary.avg_30d_year_ago !== null
            ? `vs ${summary.avg_30d_year_ago} a year ago`
            : "no year-ago baseline"}
          chip={<YoYChip pct={summary.yoy_delta_pct} />}
        />
        <KPICard
          label="Active days MTD"
          value={`${summary.days_with_intrusions_mtd}/${summary.mtd_days_observed}`}
          sublabel="days with any intrusion"
        />
      </div>

      {/* Daily bars + 7d rolling */}
      <SectionHeader right="Last 90 days">
        Daily Incursions
      </SectionHeader>
      <DailyBarsChart rows={last90} />

      {/* ADIZ schematic */}
      <SectionHeader right="Last 30 days">
        ADIZ Sector Activity
      </SectionHeader>
      <ADIZSchematic rows={rows} zoneLabels={zones} />
      <p style={{
        fontFamily: "var(--font-body)",
        fontSize: "11.5px",
        color: "var(--text-secondary)",
        lineHeight: 1.55,
        marginTop: "12px",
        maxWidth: "780px",
      }}>
        <strong style={{ color: "var(--text-primary)" }}>What is an ADIZ?</strong>{" "}
        An Air Defence Identification Zone is a unilaterally-declared
        airspace beyond a state's territorial sea (12 nm) in which the
        declaring state demands identification of approaching civil and
        military aircraft. Taiwan's ADIZ, declared by the US in the 1950s
        and inherited by the ROC, notionally extends well west of the
        median line over parts of Fujian — but the MND only counts PLA
        activity in the eastern, southern, and northern portions of the
        ADIZ, not over mainland China itself. Sorties that cross the
        median line of the strait (the dashed line above) <em>or</em>
        enter the monitored ADIZ flow into the "intruded" count. Sector
        pills show the share of the last 30 reporting days in which any
        aircraft entered each named MND sector
        (北/中/西南/東南/東).
      </p>

      {/* Vessel + coast guard */}
      <SectionHeader right="MND-era only">
        PLA Vessels &amp; Coast Guard
      </SectionHeader>
      <p style={{
        fontFamily: "var(--font-mono)",
        fontSize: "10.5px",
        color: "var(--text-muted)",
        margin: "0 0 4px",
      }}>
        Vessel counts begin when MND coverage starts ({rows.find((r) => r.vessels_total !== null && r.vessels_total !== undefined)?.date || "—"}).
        PLATracker never published these.
      </p>
      <VesselSparkline rows={last90} />

      {/* 365-day heatmap */}
      <SectionHeader right="365 days">
        Year View · Aircraft Intruded
      </SectionHeader>
      <Heatmap rows={rows} />

      <p style={{
        fontFamily: "var(--font-mono)",
        fontSize: "10px",
        color: "var(--text-muted)",
        marginTop: "32px",
        lineHeight: 1.5,
      }}>
        <strong style={{ color: "var(--text-secondary)" }}>Sources:</strong> Live scrape of MND's
        "中共解放軍臺海周邊海、空域動態" daily press releases (報告日 0600–0600).
        Historical aircraft-intruded counts from the public PLATracker dataset (Gerald C. Brown);
        PLATracker only publishes the median-line/ADIZ-entry count — vessels, coast-guard
        figures, and zone breakdowns become available the day MND coverage begins.
      </p>

      {/* ============ EXERCISE TRACKER (Phase 2b.2) ============ */}
      <SectionHeader right={exercises ? `${filteredExercises.length} approved` : "—"}>
        Exercise Tracker
      </SectionHeader>

      <p style={{
        fontFamily: "var(--font-body)",
        fontSize: "13px",
        color: "var(--text-secondary)",
        lineHeight: 1.55,
        margin: "0 0 14px",
      }}>
        Cross-strait military exercises and drills extracted from MIL_EXERCISE
        articles by the AI pipeline and editorially approved before display.
        Markers show where the activity took place; the list below includes
        approved exercises whose location could not be confidently geocoded.
        Performer pills filter both views.
      </p>

      <ExerciseFilters
        filters={exFilters}
        setFilters={setExFilters}
        counts={performerCounts}
        pendingCount={pendingCount}
        onOpenReview={() => setReviewOpen(true)}
      />

      <div style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 1.4fr) minmax(280px, 1fr)",
        gap: "16px",
        alignItems: "start",
      }}>
        <ExerciseMap
          rows={filteredExercises}
          selectedId={selectedExerciseId}
          onEdit={setEditingExercise}
          onQuickDismiss={handleQuickDismiss}
        />
        <ExerciseList
          rows={filteredExercises}
          selectedId={selectedExerciseId}
          onSelect={setSelectedExerciseId}
          onEdit={setEditingExercise}
          onQuickDismiss={handleQuickDismiss}
        />
      </div>

      <p style={{
        fontFamily: "var(--font-mono)",
        fontSize: "10px",
        color: "var(--text-muted)",
        marginTop: "16px",
        lineHeight: 1.5,
      }}>
        Map basemap: CartoDB Positron (&copy; OpenStreetMap contributors, &copy; CARTO).
        Coordinates are AI-extracted from article text and analyst-confirmed; exercises
        without a confidently-parseable location appear in the list only.
      </p>

      {reviewOpen && (
        <ExerciseReviewQueue
          onClose={() => { setReviewOpen(false); loadPendingCount();
                           fetchMilitaryExercises({ days: exFilters.days })
                             .then((r) => setExercises(r.rows || [])); }}
          onResolveAll={() => setPendingCount(0)}
        />
      )}

      {editingExercise && (
        <ExerciseEditModal
          exercise={editingExercise}
          onClose={() => setEditingExercise(null)}
          onSaved={handleExerciseSaved}
          onDismissed={handleExerciseDismissed}
        />
      )}
    </main>
  );
}
