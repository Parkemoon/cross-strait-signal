const TOPICS = [
  "MIL_EXERCISE", "MIL_MOVEMENT", "MIL_HARDWARE", "MIL_POLICY",
  "ARMS_SALES", "MARITIME_GREY", "SEC_LAWFARE", "INFO_CYBER",
  "POL_TONGDU", "CROSS_STRAIT_REG", "CULTURE", "UNITED_FRONT_INTEG", "PARTY_VISIT",
  "US_RELATIONS", "INTL_RELATIONS", "DIP_VISIT", "INT_ORG", "DIP_SANCTIONS",
  "POL_DOMESTIC_TW", "POL_DOMESTIC_PRC", "HK_MAC",
  "ECON_TRADE", "SCI_TECH", "TRANSPORT",
];

const TOPIC_LABELS = {
  MIL_EXERCISE:       "Military Exercise",
  MIL_MOVEMENT:       "Force Movement",
  MIL_HARDWARE:       "Hardware",
  MIL_POLICY:         "Mil. Policy",
  ARMS_SALES:         "Arms Sales",
  MARITIME_GREY:      "Maritime Grey-Zone",
  SEC_LAWFARE:        "Espionage & Lawfare",
  INFO_CYBER:         "Info & Cyber",
  POL_TONGDU:         "統獨 Spectrum",
  CROSS_STRAIT_REG:   "Cross-Strait Reg.",
  CULTURE:            "Culture & Society",
  UNITED_FRONT_INTEG: "United Front & Forums",
  PARTY_VISIT:        "Party Visit",
  US_RELATIONS:       "US Relations",
  INTL_RELATIONS:     "Third-Country Dip.",
  DIP_VISIT:          "Diplomatic Visit",
  INT_ORG:            "Intl Organisations",
  DIP_SANCTIONS:      "Sanctions",
  POL_DOMESTIC_TW:    "TW Politics",
  POL_DOMESTIC_PRC:   "PRC Politics",
  HK_MAC:             "HK/Macao",
  ECON_TRADE:         "Trade & Economy",
  SCI_TECH:           "Science & Technology",
  TRANSPORT:          "Transport",
};

export default function FilterBar({ filters, setFilters, topEntities }) {
  const update = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value || undefined }));
  };

  const selectStyle = {
    background: "transparent",
    color: "var(--muted)",
    border: "none",
    borderBottom: "1px solid var(--hair)",
    borderRadius: 0,
    padding: "5px 2px",
    fontSize: "10px",
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    fontFamily: "var(--font-mono)",
    cursor: "pointer",
    appearance: "auto",
  };

  return (
    <div
      style={{
        display: "flex",
        gap: "8px",
        flexWrap: "wrap",
        marginBottom: "16px",
        alignItems: "center",
        paddingBottom: "10px",
        borderBottom: "1px solid var(--hair)",
      }}
    >
      <select
        value={filters.topic || ""}
        onChange={(e) => update("topic", e.target.value)}
        style={selectStyle}
      >
        <option value="">All Topics</option>
        {TOPICS.map((t) => (
          <option key={t} value={t}>
            {TOPIC_LABELS[t] || t}
          </option>
        ))}
      </select>

      <select
        value={filters.sentiment || ""}
        onChange={(e) => update("sentiment", e.target.value)}
        style={selectStyle}
      >
        <option value="">All Sentiment</option>
        <option value="hostile">Hostile</option>
        <option value="cooperative">Cooperative</option>
        <option value="neutral">Neutral</option>
        <option value="mixed">Mixed</option>
      </select>

      <select
        value={filters.source_place || ""}
        onChange={(e) => update("source_place", e.target.value)}
        style={selectStyle}
      >
        <option value="">All Sources</option>
        <option value="PRC">PRC Sources</option>
        <option value="TW">Taiwan Sources</option>
        <option value="hk">HK/Macao Sources</option>
        <option value="intl">International Sources</option>
      </select>

      <select
        value={filters.bias || ""}
        onChange={(e) => update("bias", e.target.value)}
        style={selectStyle}
      >
        <option value="">All Bias</option>
        <option value="green">Green</option>
        <option value="green_leaning">Green-leaning</option>
        <option value="blue">Blue</option>
        <option value="blue_leaning">Blue-leaning</option>
        <option value="centrist">Centrist</option>
        <option value="china_centrist">Centrist (China-leaning)</option>
        <option value="state_official">State (official)</option>
        <option value="state_nationalist">State (nationalist)</option>
      </select>

      {topEntities && topEntities.length > 0 && (
        <select
          value={filters.entity || ""}
          onChange={(e) => update("entity", e.target.value)}
          style={selectStyle}
        >
          <option value="">All Entities</option>
          {topEntities.map((e) => (
            <option key={e.entity_name_en} value={e.entity_name_en}>
              {e.entity_name_en}
            </option>
          ))}
        </select>
      )}

      <label
        style={{
          display: "flex",
          alignItems: "center",
          gap: "5px",
          fontSize: "10px",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "var(--muted)",
          cursor: "pointer",
          fontFamily: "var(--font-mono)",
          padding: "0 4px",
        }}
      >
        <input
          type="checkbox"
          checked={filters.escalation_only || false}
          onChange={(e) =>
            update("escalation_only", e.target.checked || undefined)
          }
          style={{ accentColor: "var(--ink)" }}
        />
        Signals only
      </label>

      {Object.values(filters).some(v => v !== undefined && v !== false && v !== "") && (
        <button
          onClick={() => setFilters({})}
          style={{
            background: "transparent",
            color: "var(--muted)",
            border: "none",
            padding: "5px 2px",
            fontSize: "10px",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            fontFamily: "var(--font-mono)",
            cursor: "pointer",
          }}
        >
          {"✕ Clear filters"}
        </button>
      )}

      <input
        type="text"
        placeholder="SEARCH…"
        value={filters.search || ""}
        onChange={(e) => update("search", e.target.value)}
        style={{
          ...selectStyle,
          minWidth: "160px",
          marginLeft: "auto",
        }}
      />
    </div>
  );
}