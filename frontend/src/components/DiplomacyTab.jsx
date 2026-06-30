import { useEffect, useMemo, useState } from "react";
import {
  fetchDiplomacyMap,
  fetchDiplomacySummary,
  fetchDiplomacyStatements,
  fetchDiplomacyCandidatesCount,
} from "../api";
import DiplomacyMap, {
  BAND_COLOUR, BAND_LABEL, BAND_ORDER, TIER_LABEL,
} from "./DiplomacyMap";
import DiplomacyReviewQueue from "./DiplomacyReviewQueue";
import DiplomacyEditModal from "./DiplomacyEditModal";
import { READ_ONLY } from "../readOnly";

const OFFICIAL_TIERS = new Set(["government", "head_of_state"]);

function SectionHeader({ children, right }) {
  return (
    <div style={{ marginBottom: "16px", marginTop: "28px" }}>
      <div style={{ height: "2px", background: "var(--border-color)", marginBottom: "9px" }} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{
          fontFamily: "var(--font-mono)", fontSize: "11px", fontWeight: 600,
          letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--text-primary)",
        }}>
          {children}
        </span>
        {right && (
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)" }}>
            {right}
          </span>
        )}
      </div>
      <div style={{ height: "1px", background: "var(--border-color)", marginTop: "9px" }} />
    </div>
  );
}

function KPICard({ value, label, sublabel, accent }) {
  return (
    <div style={{ padding: "14px 16px", border: "1px solid var(--border-color)", background: "var(--bg-card)", minWidth: 0 }}>
      <div style={{
        fontFamily: "var(--font-mono)", fontSize: "10px", letterSpacing: "0.08em",
        textTransform: "uppercase", color: "var(--text-muted)", marginBottom: "6px",
      }}>
        {label}
      </div>
      <div style={{
        fontFamily: "var(--font-display)", fontSize: "26px", fontWeight: 500,
        color: accent || "var(--text-primary)", lineHeight: 1.1,
      }}>
        {value}
      </div>
      {sublabel && (
        <div style={{ fontFamily: "var(--font-body)", fontSize: "11px", color: "var(--text-secondary)", marginTop: "4px" }}>
          {sublabel}
        </div>
      )}
    </div>
  );
}

// Stacked distribution bar across the five bands — doubles as the map legend.
function StanceBar({ bands }) {
  const total = BAND_ORDER.reduce((s, b) => s + (bands[b] || 0), 0);
  return (
    <div>
      <div style={{ display: "flex", height: "16px", border: "1px solid var(--border-color)", overflow: "hidden" }}>
        {BAND_ORDER.map((b) => {
          const n = bands[b] || 0;
          if (!n) return null;
          return (
            <div key={b} title={`${BAND_LABEL[b]}: ${n}`}
              style={{ width: `${(n / total) * 100}%`, background: BAND_COLOUR[b] }} />
          );
        })}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "12px", marginTop: "10px" }}>
        {BAND_ORDER.map((b) => (
          <span key={b} style={{
            display: "inline-flex", alignItems: "center", gap: "5px",
            fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-secondary)",
          }}>
            <span style={{ width: "11px", height: "11px", background: BAND_COLOUR[b], display: "inline-block" }} />
            {BAND_LABEL[b]} ({bands[b] || 0})
          </span>
        ))}
        <span style={{
          display: "inline-flex", alignItems: "center", gap: "5px",
          fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)",
        }}>
          <span style={{ width: "11px", height: "11px", border: "1.5px dashed #d4a94a", display: "inline-block" }} />
          Divergence flagged
        </span>
      </div>
    </div>
  );
}

function StanceChip({ label }) {
  return (
    <span style={{
      fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: "0.05em",
      textTransform: "uppercase", color: "#fff", background: BAND_COLOUR[label] || "#9aa0a6",
      padding: "1px 6px", whiteSpace: "nowrap",
    }}>
      {BAND_LABEL[label] || label}
    </span>
  );
}

// Sorts countries pro-Taipei → pro-Beijing (fill stance desc), pins-only last.
function sortByStance(countries) {
  return [...countries].sort((a, b) => {
    if (a.fill && b.fill) return b.fill.stance - a.fill.stance;
    if (a.fill) return -1;
    if (b.fill) return 1;
    return b.total_count - a.total_count;
  });
}

function CountryRow({ country, selected, onSelect }) {
  return (
    <div
      onClick={() => onSelect(country.country_iso)}
      style={{
        padding: "8px 12px",
        borderLeft: selected
          ? `3px solid ${country.fill ? BAND_COLOUR[country.fill.stance_label] : "#9aa0a6"}`
          : "3px solid transparent",
        borderBottom: "1px solid var(--border-color)",
        background: selected ? "rgba(0,0,0,0.03)" : "transparent",
        cursor: "pointer", fontFamily: "var(--font-mono)", fontSize: "11px",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "8px" }}>
        <span style={{ fontFamily: "var(--font-display, serif)", fontSize: "13px", color: "var(--text-primary)" }}>
          {country.country_name}
          {country.divergent && (
            <span title="Divergence flagged" style={{ color: "#d4a94a", marginLeft: "6px" }}>◆</span>
          )}
        </span>
        {country.fill
          ? <StanceChip label={country.fill.stance_label} />
          : <span style={{ fontSize: "9px", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              pins only
            </span>}
      </div>
      <div style={{ color: "var(--text-muted)", marginTop: "2px", display: "flex", justifyContent: "space-between" }}>
        <span>
          {country.fill ? TIER_LABEL[country.fill.authority_tier] : `${country.pins_count} non-official`}
        </span>
        <span>{country.fill?.effective_date || ""}</span>
      </div>
    </div>
  );
}

// One statement line — stance chip + attribution + quote + source. Shared by
// the official-set and non-official-voice lists below. When `onEdit` is passed
// (admin only) a ✎ opens the post-approval edit modal for this exact row.
function StatementRow({ s, onEdit }) {
  return (
    <div style={{ display: "flex", gap: "10px", alignItems: "flex-start" }}>
      <div style={{ flexShrink: 0, marginTop: "2px" }}><StanceChip label={s.stance_label} /></div>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "10.5px", color: "var(--text-secondary)" }}>
          {s.speaker || "—"} · {TIER_LABEL[s.authority_tier] || s.authority_tier} · {s.effective_date}
        </div>
        <p style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--text-primary)", lineHeight: 1.45, margin: "3px 0 0" }}>
          {s.statement_en}
        </p>
        {s.article?.url && (
          <a href={s.article.url} target="_blank" rel="noreferrer"
            style={{ fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--text-muted)", textDecoration: "underline" }}>
            via {s.article.source_name}
          </a>
        )}
      </div>
      {onEdit && (
        <button onClick={() => onEdit(s)} title="Edit this statement"
          style={{
            flexShrink: 0, alignSelf: "flex-start", background: "none",
            border: "1px solid var(--border-color)", color: "var(--text-muted)",
            cursor: "pointer", fontSize: "10px", lineHeight: 1, padding: "3px 6px",
            fontFamily: "var(--font-mono)",
          }}>
          ✎
        </button>
      )}
    </div>
  );
}

// A titled statement list with loading / empty states. `loading` true while
// the fetch is in flight.
function StatementList({ title, accent, items, loading, onEdit }) {
  return (
    <div style={{ marginTop: "16px", paddingTop: "12px", borderTop: "1px dotted var(--border-color)" }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-muted)", marginBottom: "8px" }}>
        {accent}{title} {loading ? "…" : `(${items.length})`}
      </div>
      {loading ? (
        <p style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-muted)" }}>Loading…</p>
      ) : items.length === 0 ? (
        <p style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-muted)" }}>None on record.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {items.map((s) => <StatementRow key={s.id} s={s} onEdit={onEdit} />)}
        </div>
      )}
    </div>
  );
}

// Drill-in detail for the selected country. Fetches /statements over the SAME
// 730-day window the map aggregate uses, so the "Official statements" list IS
// exactly the set averaged into the fill — click in and see every story
// behind the colour. Non-official voices carry the divergence headline.
function SelectedDetail({ iso, country, onEdit, refreshNonce }) {
  const [statements, setStatements] = useState(null);
  useEffect(() => {
    if (!iso) return undefined;
    let alive = true;
    setStatements(null);
    fetchDiplomacyStatements({ country: iso, days: 730, limit: 200 })
      .then((r) => { if (alive) setStatements(r.rows || []); })
      .catch(() => { if (alive) setStatements([]); });
    return () => { alive = false; };
  }, [iso, refreshNonce]);

  if (!country) return null;
  const fill = country.fill;
  const loading = statements === null;
  const all = statements || [];
  const official = all.filter((s) => OFFICIAL_TIERS.has(s.authority_tier));
  const nonOfficial = all.filter((s) => !OFFICIAL_TIERS.has(s.authority_tier));

  return (
    <div style={{ border: "1px solid var(--border-color)", background: "var(--bg-card)", padding: "16px 18px", marginTop: "16px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "10px", flexWrap: "wrap" }}>
        <span style={{ fontFamily: "var(--font-display, serif)", fontSize: "18px", color: "var(--text-primary)" }}>
          {country.country_name}
        </span>
        {fill && <StanceChip label={fill.stance_label} />}
      </div>

      <div style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--text-secondary)", marginTop: "8px", lineHeight: 1.5 }}>
        {fill
          ? <>Aggregate posture · average of <strong style={{ color: "var(--text-primary)" }}>{fill.official_count}</strong> official statement{fill.official_count === 1 ? "" : "s"} in the trailing 24 months → <strong style={{ color: BAND_COLOUR[fill.stance_label] }}>{BAND_LABEL[fill.stance_label]}</strong>.</>
          : <>No official government or head-of-state statement on record in this window — {country.pins_count} non-official voice{country.pins_count === 1 ? "" : "s"} only.</>}
      </div>

      {fill && (
        <StatementList title="Official statements (averaged)" items={official} loading={loading} onEdit={onEdit} />
      )}
      <StatementList
        title="Non-official voices"
        accent={country.divergent ? <span style={{ color: "#b8860b" }}>◆ Divergence · </span> : null}
        items={nonOfficial}
        loading={loading}
        onEdit={onEdit}
      />
    </div>
  );
}

export default function DiplomacyTab() {
  const [mapData, setMapData] = useState(null);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(false);
  const [selectedIso, setSelectedIso] = useState(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);
  const [showPins, setShowPins] = useState(true);
  const [editing, setEditing] = useState(null);   // approved statement being edited (admin)
  const [detailNonce, setDetailNonce] = useState(0); // bump to refetch the drill-in after an edit

  const reloadMap = () => {
    Promise.all([fetchDiplomacyMap({ stale_days: 730 }), fetchDiplomacySummary({ stale_days: 730 })])
      .then(([m, s]) => { setMapData(m); setSummary(s); })
      .catch(() => setError(true));
  };
  const loadPendingCount = () => {
    if (READ_ONLY) return;
    fetchDiplomacyCandidatesCount()
      .then((r) => setPendingCount(r.pending || 0))
      .catch(() => setPendingCount(0));
  };

  useEffect(() => { reloadMap(); loadPendingCount(); }, []);

  const sortedCountries = useMemo(
    () => (mapData ? sortByStance(mapData.countries) : []),
    [mapData],
  );
  const selectedCountry = useMemo(
    () => (mapData ? mapData.countries.find((c) => c.country_iso === selectedIso) : null),
    [mapData, selectedIso],
  );

  if (error) {
    return (
      <main style={{ padding: "28px 32px" }}>
        <p style={{ color: "var(--accent-red)", fontFamily: "var(--font-mono)", fontSize: "13px", padding: "40px 0" }}>
          Couldn't load diplomatic stance data.
        </p>
      </main>
    );
  }
  if (!mapData || !summary) {
    return (
      <main style={{ padding: "28px 32px" }}>
        <p style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: "13px", padding: "40px 0" }}>
          Loading diplomatic stances…
        </p>
      </main>
    );
  }

  const bands = summary.by_band || {};
  const taipei = (bands.pro_taipei || 0) + (bands.leaning_taipei || 0);
  const beijing = (bands.pro_beijing || 0) + (bands.leaning_beijing || 0);

  return (
    <main style={{ padding: "28px 32px", minWidth: 0 }}>
      <SectionHeader right={`as of ${summary.as_of}`}>
        Third-Country Diplomatic Stance
      </SectionHeader>

      <p style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--text-secondary)", lineHeight: 1.55, margin: "0 0 18px", maxWidth: "820px" }}>
        Where the rest of the world sits on the Taiwan question — a{" "}
        <strong style={{ color: "var(--text-primary)" }}>separate axis</strong> from the
        cross-strait sentiment instrument, which deliberately discards third-party
        interactions. Each country is filled by the{" "}
        <strong style={{ color: "var(--text-primary)" }}>average of its recent government / head-of-state statements</strong>{" "}
        (the honest national posture, robust to any single stray quote). A{" "}
        <span style={{ color: "#b8860b" }}>◆ gold dashed</span> border flags a{" "}
        <strong style={{ color: "var(--text-primary)" }}>divergence</strong> — a legislator,
        party, or sub-national voice pulling against the official line. Coverage begins in
        late 2025 (the corpus start); an un-filled country is{" "}
        <em>un-tracked in this window, not neutral</em>.
      </p>

      {/* KPI strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: "12px" }}>
        <KPICard label="Countries tracked" value={summary.countries_tracked}
                 sublabel="with an official posture" />
        <KPICard label="Leaning Taipei" value={taipei} accent={BAND_COLOUR.pro_taipei}
                 sublabel="pro + leaning" />
        <KPICard label="Leaning Beijing" value={beijing} accent={BAND_COLOUR.pro_beijing}
                 sublabel="pro + leaning" />
        <KPICard label="Divergences" value={summary.divergent_count} accent="#b8860b"
                 sublabel="official vs other voices" />
      </div>

      {/* Distribution bar / legend */}
      <SectionHeader right={`${summary.countries_tracked} with posture`}>
        Stance Distribution
      </SectionHeader>
      <StanceBar bands={bands} />

      {/* Map + country list */}
      <SectionHeader right={mapData.countries.length ? `${mapData.countries.length} countries` : "—"}>
        World Map
      </SectionHeader>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px", flexWrap: "wrap", marginBottom: "10px" }}>
        <button onClick={() => setShowPins((v) => !v)}
                title="Toggle the non-official voices pin layer"
                style={{
                  padding: "4px 11px", fontFamily: "var(--font-mono)", fontSize: "10px",
                  letterSpacing: "0.06em",
                  border: "1px solid var(--border-color)",
                  background: showPins ? "var(--bg-card)" : "transparent",
                  color: showPins ? "var(--text-primary)" : "var(--text-muted)",
                  cursor: "pointer",
                }}>
          {showPins ? "◉" : "○"} Voices pins {showPins ? "on" : "off"}
        </button>
        {!READ_ONLY && (
          <button onClick={() => setReviewOpen(true)}
                  title={`${pendingCount} statements pending review`}
                  style={{
                    padding: "4px 11px", fontFamily: "var(--font-mono)", fontSize: "10px",
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
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.5fr) minmax(260px, 1fr)", gap: "16px", alignItems: "start" }}>
        <DiplomacyMap
          countries={mapData.countries}
          selectedIso={selectedIso}
          showPins={showPins}
          onSelect={(iso) => setSelectedIso((cur) => (cur === iso ? null : iso))}
        />
        <div style={{ maxHeight: "520px", overflowY: "auto", border: "1px solid var(--border-color)", background: "var(--bg-card)" }}>
          {sortedCountries.length === 0 ? (
            <div style={{ padding: "20px", fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-muted)", textAlign: "center" }}>
              No approved statements yet.
            </div>
          ) : (
            sortedCountries.map((c) => (
              <CountryRow key={c.country_iso} country={c}
                          selected={c.country_iso === selectedIso}
                          onSelect={(iso) => setSelectedIso((cur) => (cur === iso ? null : iso))} />
            ))
          )}
        </div>
      </div>

      {selectedCountry && (
        <SelectedDetail
          iso={selectedIso}
          country={selectedCountry}
          onEdit={READ_ONLY ? undefined : setEditing}
          refreshNonce={detailNonce}
        />
      )}

      <p style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)", marginTop: "16px", lineHeight: 1.5 }}>
        Basemap: Natural Earth 1:110m (public domain) via CartoDB Positron tiles
        (&copy; OpenStreetMap contributors, &copy; CARTO). The country fill is the
        official posture; <strong style={{ color: "var(--text-primary)" }}>dots</strong>{" "}
        mark countries with non-official voices (legislators, parties, sub-national
        officials), coloured by those voices' aggregate stance — a dot whose colour
        contrasts with its country fill is the divergence (also flagged by the gold
        dashed border). Microstates too small to render as polygons (Singapore, Holy
        See, several Pacific/Caribbean allies) appear as markers. Stance is
        AI-extracted from article text and analyst-approved before display.
      </p>

      {reviewOpen && (
        <DiplomacyReviewQueue
          onClose={() => { setReviewOpen(false); reloadMap(); loadPendingCount(); }}
          onResolveAll={() => setPendingCount(0)}
        />
      )}

      {editing && (
        <DiplomacyEditModal
          statement={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); reloadMap(); setDetailNonce((n) => n + 1); }}
          onDismissed={() => { setEditing(null); reloadMap(); setDetailNonce((n) => n + 1); }}
        />
      )}
    </main>
  );
}
