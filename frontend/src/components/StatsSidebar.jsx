import { SentimentTrendChart, TopicBreakdownChart } from "./SignalCharts";

const PUBLICATION_NAMES = {
  // Liberty Times
  "LTN Politics":      "Liberty Times",
  "LTN World":         "Liberty Times",
  "LTN Business":      "Liberty Times",
  "LTN Defence":       "Liberty Times",
  // CNA
  "CNA Politics":      "CNA",
  "CNA Mainland":      "CNA",
  "CNA International": "CNA",
  "CNA Finance":       "CNA",
  // United Daily News
  "UDN":               "United Daily News",
  "UDN Breaking":      "United Daily News",
  "UDN International": "United Daily News",
  "UDN Business":      "United Daily News",
  // China Times
  "CT Cross-Strait":   "China Times",
  "CT Politics":       "China Times",
  "CT Military":       "China Times",
  "CT Opinion":        "China Times",
  // Single-feed sources — display names
  "YDN":                     "Youth Daily News",
  "Xinhua Chinese":          "Xinhua",
  "People's Daily Politics": "People's Daily",
  "China News Service":      "China News Service",
  "Global Times":            "Global Times",
  "The Paper":               "The Paper",
  "PRC MFA Spokesperson":    "MFA Spokesperson",
  "Taiwan Affairs Office":   "Taiwan Affairs Office",
  "Guancha":                 "Guancha",
  "Haixia Daobao":           "Haixia Daobao",
  "PLA Daily":               "PLA Daily",
  "Zaobao Cross-Strait":     "Zaobao",
  "BBC Chinese":             "BBC Chinese",
  "RTHK Greater China":      "RTHK",
  // Ming Pao
  "Ming Pao Cross-Strait":   "Ming Pao",
  "Ming Pao Editorial":      "Ming Pao",
  "Ming Pao Opinion":        "Ming Pao",
};

const BIAS_COLORS = {
  state_nationalist: "#b91c1c",
  state_official:    "#dc2626",
  green:             "#15803d",
  green_leaning:     "#4ade80",
  blue:              "#1d4ed8",
  blue_leaning:      "#93c5fd",
  centrist:          "#6b7280",
};

// Short labels for scope chip — matches FilterBar display values
const TOPIC_SHORT = {
  MIL_EXERCISE:    "Mil Exercise",
  MIL_MOVEMENT:    "Force Movement",
  MIL_HARDWARE:    "Hardware",
  MIL_POLICY:      "Mil. Policy",
  DIP_STATEMENT:   "Diplomacy",
  DIP_VISIT:       "State Visit",
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

function buildScopeLabel(filters) {
  const parts = [];
  if (filters.topic)        parts.push(TOPIC_SHORT[filters.topic]   || filters.topic);
  if (filters.source_place) parts.push(PLACE_SHORT[filters.source_place.toLowerCase()] || filters.source_place);
  if (filters.urgency)      parts.push(URGENCY_SHORT[filters.urgency] || filters.urgency);
  if (filters.escalation_only) parts.push("Escalation");
  if (filters.entity)       parts.push(filters.entity);
  return parts.join(" · ");
}

function hasScopingFilter(filters) {
  return !!(
    filters.topic ||
    filters.source_place ||
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

function StabilityGauge({ label, score, days, compact, globalScore }) {
  const safeScore  = score ?? 0;
  const color = safeScore > 0.3
    ? "#f59e0b"
    : safeScore < -0.3
    ? "#7c3aed"
    : "#6b7280";

  // Show ghost only when global differs meaningfully from scoped
  const showGhost = globalScore !== undefined &&
                    globalScore !== null &&
                    Math.abs(globalScore - safeScore) > 0.01;

  return (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid var(--border-color)",
      borderRadius: "3px",
      padding: compact ? "10px 12px" : "14px 16px",
      marginBottom: "8px",
    }}>
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginBottom: "8px",
      }}>
        <span style={{
          fontSize: "10px",
          fontFamily: "var(--font-mono)",
          color: "var(--text-muted)",
          textTransform: "uppercase",
          letterSpacing: "1px",
        }}>
          {label}
        </span>
        <span style={{
          fontSize: compact ? "13px" : "16px",
          fontFamily: "var(--font-mono)",
          fontWeight: 600,
          color,
        }}>
          {safeScore > 0 ? "+" : ""}{safeScore.toFixed(2)}
        </span>
      </div>
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        marginBottom: "6px",
        fontSize: "9px",
        fontFamily: "var(--font-mono)",
        color: "var(--text-muted)",
      }}>
        <span>Hostile</span>
        <span>Cooperative</span>
      </div>
      <div style={{
        height: "4px",
        background: "var(--bg-secondary)",
        borderRadius: "3px",
        position: "relative",
      }}>
        {/* Gradient track */}
        <div style={{
          position: "absolute",
          inset: 0,
          borderRadius: "3px",
          background: "linear-gradient(to right, #7c3aed, #6b7280, #f59e0b)",
          opacity: 0.25,
        }} />
        {/* Ghost dot — global baseline position */}
        {showGhost && (
          <div style={{
            position: "absolute",
            left: `${((globalScore + 1) / 2) * 100}%`,
            top: "50%",
            width: compact ? "8px" : "10px",
            height: compact ? "8px" : "10px",
            borderRadius: "50%",
            background: "#6b7280",
            transform: "translate(-50%, -50%)",
            border: "2px solid var(--bg-card)",
            opacity: 0.45,
          }} />
        )}
        {/* Main dot — scoped position */}
        <div style={{
          position: "absolute",
          left: `${((safeScore + 1) / 2) * 100}%`,
          top: "50%",
          width: compact ? "10px" : "12px",
          height: compact ? "10px" : "12px",
          borderRadius: "50%",
          background: color,
          transform: "translate(-50%, -50%)",
          border: "2px solid var(--bg-card)",
          boxShadow: "0 1px 3px rgba(0,0,0,0.15)",
          transition: "left 0.5s ease",
        }} />
      </div>
      {/* Global comparison — non-compact only, only when ghost is visible */}
      {showGhost && !compact && (
        <p style={{
          textAlign: "right",
          fontSize: "9px",
          fontFamily: "var(--font-mono)",
          color: "#6b7280",
          marginTop: "4px",
          opacity: 0.7,
        }}>
          global {globalScore > 0 ? "+" : ""}{globalScore.toFixed(2)}
        </p>
      )}
      {days && !showGhost && (
        <p style={{
          textAlign: "center",
          fontSize: "10px",
          fontFamily: "var(--font-body)",
          color: "var(--text-muted)",
          marginTop: "6px",
        }}>
          {days}-day weighted average
        </p>
      )}
    </div>
  );
}

export default function StatsSidebar({ stats, filters = {}, onTopicClick, onClearScopingFilters }) {
  if (!stats) return null;

  const isFiltered    = hasScopingFilter(filters);
  const scopeLabel    = isFiltered ? buildScopeLabel(filters) : "";

  // Build global-by-place lookup for ghost dots
  const globalByPlace = {};
  (stats.global_sentiment_by_place ?? []).forEach((r) => {
    globalByPlace[r.place] = r.avg_score;
  });

  const sectionTitle = () => ({
    fontSize: "10px",
    fontFamily: "var(--font-mono)",
    color: "var(--text-muted)",
    textTransform: "uppercase",
    letterSpacing: "2px",
    marginBottom: "14px",
    fontWeight: 500,
  });

  const MIN_CAMP_N = 5; // minimum articles to show Taiwan-by-camp gauges

  return (
    <div>
      {/* Strait Watch */}
      <div style={{ marginBottom: "28px" }}>
        <div style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "14px",
        }}>
          <h3 style={{ ...sectionTitle(), marginBottom: 0 }}>Strait Watch</h3>

          {/* Scope chip — visible only when a scoping filter is active */}
          {isFiltered && (
            <div style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              background: "rgba(26,122,109,0.1)",
              border: "1px solid rgba(26,122,109,0.35)",
              borderRadius: "3px",
              padding: "3px 8px",
              fontSize: "9px",
              fontFamily: "var(--font-mono)",
              color: "var(--accent-teal)",
              textTransform: "uppercase",
              letterSpacing: "0.5px",
              maxWidth: "160px",
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
                  color: "var(--accent-teal)",
                  padding: 0,
                  fontSize: "11px",
                  lineHeight: 1,
                  flexShrink: 0,
                  opacity: 0.8,
                }}
              >
                ×
              </button>
            </div>
          )}
        </div>

        {/* Overall gauge */}
        {isFiltered && stats.total_articles === 0 ? (
          <div style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "3px",
            padding: "20px 16px",
            marginBottom: "8px",
            textAlign: "center",
            fontSize: "11px",
            fontFamily: "var(--font-mono)",
            color: "var(--text-muted)",
          }}>
            No articles match this scope
          </div>
        ) : (
          <>
            <StabilityGauge
              label="Overall"
              score={stats.avg_sentiment_score}
              days={isFiltered ? null : stats.period_days}
              globalScore={isFiltered ? stats.global_avg_sentiment_score : undefined}
            />

            {[...(stats.sentiment_by_place ?? [])].sort((a, b) => {
                const order = { PRC: 0, TW: 1, HK: 2, INTL: 3 };
                return (order[a.place] ?? 4) - (order[b.place] ?? 4);
              }).map((c) => (
              <StabilityGauge
                key={c.place}
                label={
                  c.place === "PRC"  ? "PRC Sources" :
                  c.place === "TW"   ? "Taiwan Sources" :
                  c.place === "HK"   ? "HK/Macao Sources" :
                  "International Sources"
                }
                score={c.avg_score}
                globalScore={isFiltered ? (globalByPlace[c.place] ?? undefined) : undefined}
              />
            ))}

            {/* Taiwan by camp — hidden under low N */}
            {stats.sentiment_by_bias?.length > 0 && (
              <>
                <div style={{
                  fontSize: "10px",
                  fontFamily: "var(--font-mono)",
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "1.5px",
                  marginTop: "12px",
                  marginBottom: "8px",
                }}>
                  Taiwan by camp
                </div>
                {stats.sentiment_by_bias.every((b) => (b.count ?? 0) < MIN_CAMP_N) ? (
                  <div style={{
                    fontSize: "10px",
                    fontFamily: "var(--font-mono)",
                    color: "var(--text-muted)",
                    padding: "8px 0",
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
                          b.bias === "blue"          ? "Blue" : b.bias
                        }
                        score={b.avg_score}
                        compact
                      />
                    )
                  ))
                )}
              </>
            )}
          </>
        )}
      </div>

      {/* Stability Trend Chart */}
      <SentimentTrendChart
        data={stats.sentiment_trend}
        days={stats.period_days}
      />

      {/* Topic Breakdown Chart — hidden when a topic filter is active (one bar = useless) */}
      {!filters.topic && (
        <TopicBreakdownChart
          data={stats.topics}
          onTopicClick={onTopicClick}
        />
      )}

      {/* Source Health */}
      <div style={{ marginBottom: "28px" }}>
        <h3 style={sectionTitle()}>Sources</h3>
        <div style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "3px",
          padding: "12px 16px",
        }}>
          {groupSources(stats.sources ?? []).map((s, i, arr) => (
            <div
              key={s.name}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "5px 0",
                borderBottom: i < arr.length - 1
                  ? "1px solid var(--border-color)"
                  : "none",
              }}
            >
              <span style={{
                fontSize: "13px",
                fontFamily: "var(--font-body)",
                color: "var(--text-secondary)",
                display: "flex",
                alignItems: "center",
                gap: "6px",
              }}>
                <span style={{
                  width: "8px",
                  height: "8px",
                  borderRadius: "50%",
                  background: BIAS_COLORS[s.bias] || "#6b7280",
                  display: "inline-block",
                }} />
                {s.name}
              </span>
              <span style={{
                fontFamily: "var(--font-mono)",
                fontSize: "12px",
                color: "var(--text-muted)",
              }}>
                {s.count}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Key Entities */}
      <div>
        <h3 style={sectionTitle()}>Key Entities</h3>
        <div style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "3px",
          padding: "12px 16px",
        }}>
          {stats.top_entities?.slice(0, 10).map((e, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "4px 0",
                borderBottom: i < Math.min(stats.top_entities.length, 10) - 1
                  ? "1px solid var(--border-color)"
                  : "none",
              }}
            >
              <span style={{
                fontSize: "13px",
                fontFamily: "var(--font-body)",
                color: "var(--text-secondary)",
              }}>
                {e.entity_name_en}
                <span style={{
                  fontSize: "10px",
                  color: "var(--text-muted)",
                  fontFamily: "var(--font-mono)",
                  marginLeft: "6px",
                }}>
                  {e.entity_type}
                </span>
              </span>
              <span style={{
                fontFamily: "var(--font-mono)",
                fontSize: "12px",
                color: "var(--text-muted)",
              }}>
                {e.mentions}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
