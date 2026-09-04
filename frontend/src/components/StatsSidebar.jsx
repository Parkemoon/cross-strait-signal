import { useEffect, useState } from "react";
import { SentimentTrendChart, TopicBreakdownChart } from "./SignalCharts";
import StatSpotlight from "./StatSpotlight";
import { BIAS_META, PUBLICATION_NAMES } from "./SourceBadge";
import { modelLabel, armLabel, modelTint, modelTintRgba } from "../altModels";
import { bandColour } from "../sentimentBand";
import { entityAlignment } from "../entityAlignment";
import { fetchKeyFigures } from "../api";

// Module-level cache: the roster is small and static for a session.
let rosterPromise = null;
function useKeyFigureRoster() {
  const [roster, setRoster] = useState([]);
  useEffect(() => {
    if (!rosterPromise) {
      rosterPromise = fetchKeyFigures().then((d) => d?.figures || []).catch(() => []);
    }
    let alive = true;
    rosterPromise.then((r) => { if (alive) setRoster(r); });
    return () => { alive = false; };
  }, []);
  return roster;
}

// Maps publication display name → DB source name prefix for API filtering
const SOURCE_FILTER = {
  "Liberty Times":      "LTN",
  "CNA":                "CNA",
  "United Daily News":  "UDN",
  "China Times":        "CT",
  "Youth Daily News":   "YDN",
  "Xinhua":             "Xinhua",
  "People's Daily":     "People's Daily",
  "China News Service": "China News Service",
  "Global Times":       "Global Times",
  "The Paper":          "The Paper",
  "MFA Spokesperson":   "PRC MFA",
  "Taiwan Affairs Office": "Taiwan Affairs Office",
  "China Taiwan Net":   "China Taiwan Net",
  "Guancha":            "Guancha",
  "Haixia Daobao":      "Haixia Daobao",
  "PLA Daily":          "PLA Daily",
  "Zaobao":             "Zaobao",
  "BBC Chinese":        "BBC Chinese",
  "RTHK":               "RTHK",
  "Ming Pao":           "Ming Pao",
};

// Short labels for scope chip — matches FilterBar display values
const TOPIC_SHORT = {
  MIL_EXERCISE:    "Mil Exercise",
  MIL_MOVEMENT:    "Force Movement",
  MIL_HARDWARE:    "Hardware",
  MIL_POLICY:      "Mil. Policy",
  DIP_STATEMENT:   "Diplomacy",
  DIP_VISIT:       "Diplomatic Visit",
  DIP_SANCTIONS:   "Sanctions",
  PARTY_VISIT:     "Party Visit",
  ARMS_SALES:      "Arms Sales",
  ECON_TRADE:      "Trade",
  ECON_INVEST:     "Investment",
  ENERGY:          "Energy",
  SCI_TECH:        "Sci/Tech",
  POL_DOMESTIC_TW: "TW Politics",
  POL_DOMESTIC_PRC:"PRC Politics",
  POL_TONGDU:      "統獨",
  US_PRC:          "US-PRC",
  US_TAIWAN:       "US-Taiwan",
  HK_MAC:          "HK/Macao",
  INFO_WARFARE:    "Info Warfare",
  CYBER:           "Cyber",
  LEGAL_GREY:      "Grey Zone",
  CULTURE:         "Culture",
  SPORT:           "Sport",
  TRANSPORT:       "Transport",
  INT_ORG:         "Intl Orgs",
  HUMANITARIAN:    "Humanitarian",
};

const PLACE_SHORT = {
  prc:  "PRC",
  tw:   "Taiwan",
  hk:   "HK/Macao",
  intl: "International",
};

const URGENCY_SHORT = {
  flash:    "Flash",
  priority: "Priority",
  routine:  "Routine",
};

const BIAS_SHORT = {
  green:         "Green camp",
  green_leaning: "Green-leaning",
  blue:          "Blue camp",
  blue_leaning:  "Blue-leaning",
  china_centrist:"China-centrist",
};

function buildScopeLabel(filters) {
  const parts = [];
  if (filters.topic)        parts.push(TOPIC_SHORT[filters.topic]   || filters.topic);
  if (filters.source_place) parts.push(PLACE_SHORT[filters.source_place.toLowerCase()] || filters.source_place);
  if (filters.source_name) {
    const displayName = Object.entries(SOURCE_FILTER).find(([, v]) => v === filters.source_name)?.[0] ?? filters.source_name;
    parts.push(displayName);
  }
  if (filters.bias)         parts.push(BIAS_SHORT[filters.bias] || filters.bias);
  if (filters.urgency)      parts.push(URGENCY_SHORT[filters.urgency] || filters.urgency);
  if (filters.escalation_only) parts.push("Escalation");
  if (filters.entity)       parts.push(filters.entity);
  return parts.join(" · ");
}

function hasScopingFilter(filters) {
  return !!(
    filters.topic ||
    filters.source_place ||
    filters.source_name ||
    filters.bias ||
    filters.urgency ||
    filters.escalation_only ||
    filters.entity
  );
}

function groupSources(sources) {
  const map = {};
  for (const s of sources) {
    const pub = PUBLICATION_NAMES[s.name] || s.name;
    if (map[pub]) {
      map[pub].count += s.count;
    } else {
      map[pub] = { name: pub, count: s.count, bias: s.bias };
    }
  }
  return Object.values(map).sort((a, b) => b.count - a.count);
}

// Rail section label — Archivo micro-caps over a hairline.
function RailLabel({ title, right, first }) {
  return (
    <div style={{
      display: "flex", justifyContent: "space-between", alignItems: "center",
      borderTop: first ? "none" : "1px solid var(--hair)",
      paddingTop: first ? 0 : "14px",
      marginBottom: "10px",
    }}>
      <span style={{
        fontFamily: "var(--font-mono)",
        fontSize: "9px",
        fontWeight: 600,
        letterSpacing: "0.2em",
        textTransform: "uppercase",
        color: "var(--ink)",
      }}>{title}</span>
      {right}
    </div>
  );
}

// Hairline gauge — label over a 2px track with a positioned dot, score right.
function StabilityGauge({ label, score, days, compact, globalScore, onClick, isActive }) {
  const safeScore = score ?? 0;
  const colour = bandColour(safeScore);

  // Show ghost only when global differs meaningfully from scoped
  const showGhost = globalScore !== undefined &&
                    globalScore !== null &&
                    Math.abs(globalScore - safeScore) > 0.01;

  return (
    <div
      className={onClick ? "filter-row" : undefined}
      onClick={onClick}
      title={onClick ? `Filter by ${label}` : undefined}
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 44px",
        gap: "8px",
        alignItems: "center",
        cursor: onClick ? "pointer" : "default",
      }}
    >
      <div>
        <div style={{
          fontSize: "10px",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: isActive ? "var(--ink)" : "var(--muted)",
          fontWeight: isActive ? 600 : 400,
          marginBottom: "3px",
          fontFamily: "var(--font-body)",
        }}>
          {label}{days ? <span style={{ color: "var(--pale)", textTransform: "none", letterSpacing: 0 }}> · {days}d</span> : null}
        </div>
        <div style={{ height: "2px", background: "var(--hair)", position: "relative" }}>
          {showGhost && (
            <div style={{
              position: "absolute",
              left: `${((globalScore + 1) / 2) * 100}%`,
              top: "-2px",
              width: "6px",
              height: "6px",
              borderRadius: "50%",
              background: "var(--dot)",
              transform: "translateX(-50%)",
            }} title={`global ${globalScore > 0 ? "+" : ""}${globalScore.toFixed(2)}`} />
          )}
          <div style={{
            position: "absolute",
            left: `${((safeScore + 1) / 2) * 100}%`,
            top: "-2px",
            width: "6px",
            height: "6px",
            borderRadius: "50%",
            background: colour,
            transform: "translateX(-50%)",
            transition: "left 0.5s ease",
          }} />
        </div>
      </div>
      <span style={{
        fontFamily: "var(--font-mono)",
        fontSize: "11px",
        fontWeight: 600,
        color: colour,
        textAlign: "right",
      }}>
        {safeScore > 0 ? "+" : ""}{safeScore.toFixed(2)}
      </span>
    </div>
  );
}

// Alignment legend chips — System A. TW OFFICIAL demonstrates the hollow
// (state-not-party) marker used for government bodies.
const LEGEND = [
  { label: "GREEN", colour: "var(--green)", filled: true },
  { label: "BLUE", colour: "var(--blue)", filled: true },
  { label: "PRC STATE", colour: "var(--red)", filled: true },
  { label: "TW OFFICIAL", colour: "var(--green)", filled: false },
  { label: "NATIONALIST", colour: "var(--nat)", filled: true },
  { label: "CENTRIST", colour: "var(--muted)", filled: true },
];

export default function StatsSidebar({ stats, filters = {}, altDual, onTopicClick, onPlaceClick, onSourceClick, onEntityClick, onBiasClick, onClearScopingFilters, onOpenTab }) {
  // Key-figure roster for the entity alignment markers (side + party per
  // curated person); fetched once, cached for the session.
  const figures = useKeyFigureRoster();
  if (!stats) return null;

  const isFiltered    = hasScopingFilter(filters);
  const scopeLabel    = isFiltered ? buildScopeLabel(filters) : "";
  // Server echoes the lens it applied ({model, arm} | null) — trusting the
  // response, not the request state, so the banner can never claim alt data
  // while showing production numbers (or vice versa).
  const altLens = stats.alt_lens;
  // "Both" view: overlay production Gemini (computed server-side over the
  // SAME swept subset) as ghost dots on the gauges + a dashed trend line.
  const dualBaseline = altLens && altDual ? stats.alt_baseline : null;
  const baselineByPlace = {};
  (dualBaseline?.sentiment_by_place ?? []).forEach((r) => {
    baselineByPlace[r.place] = r.avg_score;
  });

  // Build global-by-place lookup for ghost dots
  const globalByPlace = {};
  (stats.global_sentiment_by_place ?? []).forEach((r) => {
    globalByPlace[r.place] = r.avg_score;
  });

  const MIN_CAMP_N = 5; // minimum articles to show Taiwan-by-camp gauges

  return (
    <div>
      {/* Alignment legend — closes with a hairline */}
      <div style={{
        display: "flex", flexWrap: "wrap", gap: "7px 12px",
        fontFamily: "var(--font-mono)", fontSize: "8.5px", letterSpacing: "0.1em",
        color: "var(--muted)", paddingBottom: "14px", marginBottom: "16px",
        borderBottom: "1px solid var(--hair)",
      }}>
        {LEGEND.map((l) => (
          <span key={l.label} style={{ display: "flex", alignItems: "center", gap: "4px", whiteSpace: "nowrap" }}>
            <span style={{
              width: "7px", height: "7px", flexShrink: 0,
              background: l.filled ? l.colour : "transparent",
              border: l.filled ? "none" : `1px solid ${l.colour}`,
            }} />
            {l.label}
          </span>
        ))}
      </div>

      {/* Alt-model lens banner — every number below comes from the sweep */}
      {altLens && (
        <div style={{
          marginBottom: "16px",
          padding: "7px 10px",
          border: `1px solid ${modelTint(altLens.model)}`,
          background: modelTintRgba(altLens.model, 0.07),
          fontSize: "10px",
          fontFamily: "var(--font-mono)",
          color: "var(--text-primary)",
          textTransform: "uppercase",
          letterSpacing: "0.8px",
          lineHeight: 1.6,
        }}>
          <span style={{ color: modelTint(altLens.model), fontWeight: 600 }}>
            {modelLabel(altLens.model)}
          </span>
          {" "}· {armLabel(altLens.arm)}
          <div style={{ color: "var(--text-muted)", letterSpacing: "0.5px" }}>
            {dualBaseline
              ? "vs Gemini · ghost dot + dashed line = production"
              : "stats from swept articles only"}
          </div>
        </div>
      )}

      {/* Strait Watch */}
      <div style={{ marginBottom: "18px" }}>
        <RailLabel
          first
          title="Strait Watch"
          right={isFiltered && (
            <span style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              border: "1px solid var(--dot)",
              padding: "2px 7px",
              fontSize: "8.5px",
              fontFamily: "var(--font-mono)",
              color: "var(--muted)",
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              maxWidth: "150px",
            }}>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {scopeLabel}
              </span>
              <button
                onClick={onClearScopingFilters}
                title="Clear scope filters"
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "var(--muted)",
                  padding: 0,
                  fontSize: "11px",
                  lineHeight: 1,
                  flexShrink: 0,
                }}
              >
                ×
              </button>
            </span>
          )}
        />
        <div style={{
          fontFamily: "var(--font-mono)", fontSize: "8.5px",
          color: "var(--pale)", marginTop: "-6px", marginBottom: "10px",
        }}>
          ◀ HOSTILE · COOPERATIVE ▶
        </div>

        {isFiltered && stats.total_articles === 0 ? (
          <div style={{
            padding: "16px 0",
            fontSize: "11px",
            fontFamily: "var(--font-body)",
            color: "var(--muted)",
          }}>
            No articles match this scope
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "9px" }}>
            <StabilityGauge
              label="Overall"
              score={stats.avg_sentiment_score}
              days={isFiltered ? null : stats.period_days}
              globalScore={dualBaseline
                ? dualBaseline.avg_sentiment_score
                : isFiltered ? stats.global_avg_sentiment_score : undefined}
              onClick={filters.source_place && onPlaceClick ? () => onPlaceClick(null) : undefined}
              isActive={false}
            />

            {[...(stats.sentiment_by_place ?? [])].sort((a, b) => {
                const order = { PRC: 0, TW: 1, HK: 2, INTL: 3 };
                return (order[a.place] ?? 4) - (order[b.place] ?? 4);
              }).map((c) => {
                const placeKey =
                  c.place === "PRC"  ? "PRC" :
                  c.place === "TW"   ? "TW" :
                  c.place === "HK"   ? "hk" :
                  "intl";
                const placeLabel =
                  c.place === "PRC"  ? "PRC Sources" :
                  c.place === "TW"   ? "Taiwan Sources" :
                  c.place === "HK"   ? "HK/Macao Sources" :
                  "International Sources";
                return (
                  <StabilityGauge
                    key={c.place}
                    label={placeLabel}
                    score={c.avg_score}
                    globalScore={dualBaseline
                      ? (baselineByPlace[c.place] ?? undefined)
                      : isFiltered ? (globalByPlace[c.place] ?? undefined) : undefined}
                    onClick={onPlaceClick ? () => onPlaceClick(placeKey) : undefined}
                    isActive={filters.source_place === placeKey}
                  />
                );
              })}

            {/* Taiwan by camp — hidden under low N */}
            {stats.sentiment_by_bias?.length > 0 && (
              <>
                <div style={{
                  fontSize: "8.5px",
                  fontFamily: "var(--font-mono)",
                  color: "var(--pale)",
                  textTransform: "uppercase",
                  letterSpacing: "0.14em",
                  marginTop: "6px",
                }}>
                  Taiwan by camp
                </div>
                {stats.sentiment_by_bias.every((b) => (b.count ?? 0) < MIN_CAMP_N) ? (
                  <div style={{
                    fontSize: "10px",
                    fontFamily: "var(--font-body)",
                    color: "var(--muted)",
                  }}>
                    Insufficient sample
                    {" (n=" + stats.sentiment_by_bias.reduce((s, b) => s + (b.count ?? 0), 0) + ")"}
                  </div>
                ) : (
                  stats.sentiment_by_bias.map((b) => (
                    (b.count ?? 0) >= MIN_CAMP_N && (
                      <StabilityGauge
                        key={b.bias}
                        label={
                          b.bias === "green"         ? "Green" :
                          b.bias === "green_leaning" ? "Green-leaning" :
                          b.bias === "blue"          ? "Blue" :
                          b.bias === "blue_leaning"  ? "Blue-leaning" : b.bias
                        }
                        score={b.avg_score}
                        compact
                        onClick={onBiasClick ? () => onBiasClick(b.bias) : undefined}
                        isActive={filters.bias === b.bias}
                      />
                    )
                  ))
                )}
              </>
            )}
          </div>
        )}
      </div>

      {/* Trend — under the lens the line takes the model's tint; the "Both"
          view adds production Gemini as a dashed grey line */}
      <SentimentTrendChart
        data={stats.sentiment_trend}
        days={stats.period_days}
        accent={altLens ? modelTint(altLens.model) : undefined}
        baseline={dualBaseline?.sentiment_trend}
      />

      {/* Topic Breakdown — hidden when a topic filter is active (one bar = useless) */}
      {!filters.topic && (
        <TopicBreakdownChart
          data={stats.topics}
          onTopicClick={onTopicClick}
        />
      )}

      {/* Rotating stat spotlight — cycles a headline figure from each section,
          click-through to that section's tab */}
      <StatSpotlight onOpen={onOpenTab} />

      {/* Sources */}
      <div style={{ marginBottom: "18px" }}>
        <RailLabel title="Sources" />
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          {groupSources(stats.sources ?? []).map((s) => {
            const dbPrefix = SOURCE_FILTER[s.name];
            const isActive = dbPrefix && filters.source_name === dbPrefix;
            const meta = BIAS_META[s.bias];
            return (
              <div
                key={s.name}
                className={onSourceClick && dbPrefix ? "filter-row" : undefined}
                onClick={onSourceClick && dbPrefix ? () => onSourceClick(dbPrefix, s.name) : undefined}
                title={onSourceClick && dbPrefix ? `Filter by ${s.name}` : undefined}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "baseline",
                  cursor: onSourceClick && dbPrefix ? "pointer" : "default",
                }}
              >
                <span style={{
                  fontSize: "11px",
                  fontFamily: "var(--font-body)",
                  color: isActive ? "var(--ink)" : "var(--body)",
                  fontWeight: isActive ? 600 : 400,
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                }}>
                  <span style={{
                    width: "6px",
                    height: "6px",
                    borderRadius: "50%",
                    flexShrink: 0,
                    background: meta?.colour || "var(--muted)",
                    display: "inline-block",
                  }} />
                  {s.name}
                </span>
                <span style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "10px",
                  color: "var(--faint)",
                }}>
                  {s.count}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Key Entities — square markers (entities are actors, not outlets) */}
      <div>
        <RailLabel title="Key Entities" />
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          {stats.top_entities?.slice(0, 10).map((e, i) => {
            const isActive = filters.entity && e.entity_name_en &&
              e.entity_name_en.toLowerCase().includes(filters.entity.toLowerCase());
            return (
              <div
                key={i}
                className={onEntityClick ? "filter-row" : undefined}
                onClick={onEntityClick ? () => onEntityClick(e.entity_name_en) : undefined}
                title={onEntityClick ? `Filter by ${e.entity_name_en}` : undefined}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "baseline",
                  cursor: onEntityClick ? "pointer" : "default",
                }}
              >
                <span style={{
                  fontSize: "11px",
                  fontFamily: "var(--font-body)",
                  color: isActive ? "var(--ink)" : "var(--body)",
                  fontWeight: isActive ? 600 : 400,
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  minWidth: 0,
                }}>
                  {/* Alignment marker: filled = party / state organ, hollow =
                      TW government body, dot-grey = unaligned or unknown */}
                  {(() => {
                    const al = entityAlignment(e.entity_name_en, e.entity_type, figures);
                    return (
                      <span
                        title={al ? (al.hollow ? "Taiwan government body" : "Party or state organ") : undefined}
                        style={{
                          width: "6px",
                          height: "6px",
                          flexShrink: 0,
                          boxSizing: "border-box",
                          background: al ? (al.hollow ? "transparent" : al.colour) : "var(--dot)",
                          border: al && al.hollow ? `1px solid ${al.colour}` : "none",
                          display: "inline-block",
                        }}
                      />
                    );
                  })()}
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {e.entity_name_en}
                  </span>
                  <span style={{
                    fontSize: "8.5px",
                    color: "var(--pale)",
                    fontFamily: "var(--font-mono)",
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    flexShrink: 0,
                  }}>
                    {e.entity_type}
                  </span>
                </span>
                <span style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "10px",
                  color: "var(--faint)",
                }}>
                  {e.mentions}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
