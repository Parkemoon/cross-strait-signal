const TOPICS = [
  "MIL_EXERCISE", "MIL_MOVEMENT", "MIL_HARDWARE",
  "DIP_STATEMENT", "DIP_VISIT", "DIP_SANCTIONS",
  "ECON_TRADE", "ECON_INVEST",
  "POL_DOMESTIC", "POL_TONGDU",
  "INFO_WARFARE", "LEGAL_GREY", "HUMANITARIAN",
];

export default function FilterBar({ filters, setFilters }) {
  const update = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value || undefined }));
  };

  const selectStyle = {
    background: "var(--bg-card)",
    color: "var(--text-primary)",
    border: "1px solid var(--border-color)",
    borderRadius: "4px",
    padding: "6px 10px",
    fontSize: "12px",
    fontFamily: "'JetBrains Mono', 'Courier New', monospace",
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
            {t.replace(/_/g, "-")}
          </option>
        ))}
      </select>

      <select
        value={filters.sentiment || ""}
        onChange={(e) => update("sentiment", e.target.value)}
        style={selectStyle}
      >
        <option value="">All Sentiment</option>
        <option value="escalatory">Escalatory</option>
        <option value="conciliatory">Conciliatory</option>
        <option value="neutral">Neutral</option>
        <option value="ambiguous">Ambiguous</option>
      </select>

      <select
        value={filters.source_country || ""}
        onChange={(e) => update("source_country", e.target.value)}
        style={selectStyle}
      >
        <option value="">All Sources</option>
        <option value="PRC">PRC</option>
        <option value="TW">Taiwan</option>
      </select>

      <label
        style={{
          display: "flex",
          alignItems: "center",
          gap: "4px",
          fontSize: "12px",
          color: "var(--text-secondary)",
          cursor: "pointer",
          fontFamily: "'JetBrains Mono', 'Courier New', monospace",
        }}
      >
        <input
          type="checkbox"
          checked={filters.escalation_only || false}
          onChange={(e) => update("escalation_only", e.target.checked || undefined)}
        />
        Escalation signals only
      </label>

      <input
        type="text"
        placeholder="Search..."
        value={filters.search || ""}
        onChange={(e) => update("search", e.target.value)}
        style={{
          ...selectStyle,
          minWidth: "150px",
        }}
      />
    </div>
  );
}