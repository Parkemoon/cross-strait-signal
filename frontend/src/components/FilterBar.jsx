const TOPICS = [
  "MIL_EXERCISE", "MIL_MOVEMENT", "MIL_HARDWARE",
  "DIP_STATEMENT", "DIP_VISIT", "DIP_SANCTIONS", "PARTY_VISIT",
  "ECON_TRADE", "ECON_INVEST",
  "POL_DOMESTIC_TW", "POL_DOMESTIC_PRC", "POL_TONGDU",
  "INFO_WARFARE", "LEGAL_GREY", "TRANSPORT", "INT_ORG", "HUMANITARIAN",
];

const TOPIC_LABELS = {
  MIL_EXERCISE: "Military Exercise",
  MIL_MOVEMENT: "Force Movement",
  MIL_HARDWARE: "Hardware",
  DIP_STATEMENT: "Diplomacy",
  DIP_VISIT: "Official Visit",
  PARTY_VISIT: "Party Visit",
  DIP_SANCTIONS: "Sanctions",
  ECON_TRADE: "Trade",
  ECON_INVEST: "Investment",
  POL_DOMESTIC_TW: "TW Politics",
  POL_DOMESTIC_PRC: "PRC Politics",
  POL_TONGDU: "統獨 Spectrum",
  INFO_WARFARE: "Info Warfare",
  LEGAL_GREY: "Grey Zone",
  TRANSPORT: "Transport",
  INT_ORG: "Intl Organisations",
  HUMANITARIAN: "Humanitarian",
};

export default function FilterBar({ filters, setFilters, topEntities }) {
  const update = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value || undefined }));
  };

  const selectStyle = {
    background: "var(--bg-card)",
    color: "var(--text-primary)",
    border: "1px solid var(--border-color)",
    borderRadius: "3px",
    padding: "7px 12px",
    fontSize: "13px",
    fontFamily: "var(--font-body)",
    cursor: "pointer",
    appearance: "auto",
  };

  return (
    <div
      style={{
        display: "flex",
        gap: "8px",
        flexWrap: "wrap",
        marginBottom: "20px",
        alignItems: "center",
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
        <option value="destabilising">Destabilising</option>
        <option value="stabilising">Stabilising</option>
        <option value="neutral">Neutral</option>
        <option value="ambiguous">Ambiguous</option>
      </select>

      <select
        value={filters.source_country || ""}
        onChange={(e) => update("source_country", e.target.value)}
        style={selectStyle}
      >
        <option value="">All Sources</option>
        <option value="PRC">PRC Sources</option>
        <option value="TW">Taiwan Sources</option>
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
          fontSize: "13px",
          color: "var(--text-secondary)",
          cursor: "pointer",
          fontFamily: "var(--font-body)",
          padding: "0 4px",
        }}
      >
        <input
          type="checkbox"
          checked={filters.escalation_only || false}
          onChange={(e) =>
            update("escalation_only", e.target.checked || undefined)
          }
          style={{ accentColor: "var(--accent-red)" }}
        />
        Signals only
      </label>

      {Object.values(filters).some(v => v !== undefined && v !== false && v !== "") && (
        <button
          onClick={() => setFilters({})}
          style={{
            background: "transparent",
            color: "var(--text-muted)",
            border: "1px solid var(--border-color)",
            borderRadius: "3px",
            padding: "7px 12px",
            fontSize: "12px",
            fontFamily: "var(--font-mono)",
            cursor: "pointer",
          }}
        >
          {"✕ Clear filters"}
        </button>
      )}

      <input
        type="text"
        placeholder="Search articles..."
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