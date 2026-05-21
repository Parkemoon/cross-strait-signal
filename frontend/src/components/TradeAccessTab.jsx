import { useEffect, useMemo, useState } from "react";
import { fetchTradeAccessItems, fetchTradeAccessSummary } from "../api";

// Direction toggle. The DB stores who the importer is, so reading these
// rows means "what does the importer admit". Labels frame it as a flow
// to make the asymmetry obvious.
const DIRECTIONS = [
  { id: "tw_imports_from_prc", label: "PRC → Taiwan",  short: "Into TW",  blurb: "What Taiwan allows in from the mainland" },
  { id: "prc_imports_from_tw", label: "Taiwan → PRC",  short: "Into PRC", blurb: "What the mainland allows in from Taiwan" },
];

const STATUS_FILTERS = [
  { id: "",                value: null,            label: "All" },
  { id: "banned",          value: "banned",        label: "Banned" },
  { id: "ecfa_suspended",  value: "ecfa_suspended",label: "ECFA suspended" },
  { id: "partial_lift",    value: "partial_lift",  label: "Partial lift" },
  { id: "conditional",     value: "conditional",   label: "Conditional" },
  { id: "ecfa_active",     value: "ecfa_active",   label: "ECFA active" },
];

// Status presentation. Colour shading is the visual hook — banned/suspended
// dominate the right column (Into TW) for an analyst scanning the table.
// `partial_lift` uses teal — distinct from banned-red and ecfa-active-green
// to flag the political-channel-mediated middle state.
const STATUS_PILLS = {
  banned:         { label: "Banned",          dot: "#dc2626", bg: "rgba(220,38,38,0.10)",   fg: "#991b1b", border: "rgba(220,38,38,0.30)" },
  ecfa_suspended: { label: "ECFA suspended",  dot: "#f59e0b", bg: "rgba(245,158,11,0.10)",  fg: "#92400e", border: "rgba(245,158,11,0.35)" },
  partial_lift:   { label: "Partial lift",    dot: "#0d9488", bg: "rgba(13,148,136,0.10)",  fg: "#115e59", border: "rgba(13,148,136,0.35)" },
  conditional:    { label: "Conditional",     dot: "#0ea5e9", bg: "rgba(14,165,233,0.10)",  fg: "#0369a1", border: "rgba(14,165,233,0.30)" },
  ecfa_active:    { label: "ECFA active",     dot: "#16a34a", bg: "rgba(22,163,74,0.10)",   fg: "#166534", border: "rgba(22,163,74,0.30)" },
  allowed:        { label: "Allowed",         dot: "#6b7280", bg: "rgba(107,114,128,0.08)", fg: "#374151", border: "rgba(107,114,128,0.25)" },
};

// Where each source's underlying dataset / announcement lives, so users can
// audit the data origin. For curated rows the per-row ban_announcement_url
// wins (the GACC notice for that specific ban), so we fall back to a
// general project doc only if that's empty.
const SOURCE_URLS = {
  BOFT_22674:        "https://data.gov.tw/dataset/22674",
  BOFT_22675:        "https://data.gov.tw/dataset/22675",
  CUSTOMS_ECFA_2024: "https://web.customs.gov.tw/singlehtml/711?cntId=cus1_179540_711",
  MOF_PRC_SUSP_W1:   "https://gss.mof.gov.cn/gzdt/zhengcefabu/",
  MOF_PRC_SUSP_W2:   "https://gss.mof.gov.cn/gzdt/zhengcefabu/202405/t20240531_3936149.htm",
  CURATED:           null,
};

// CIFER snapshot — manually captured because the database is browser-gated
// and not API-scrapeable from this server (see CLAUDE.md). Refresh when
// re-querying ciferquery.singlewindow.cn under the 港澳台 tab.
const CIFER_SNAPSHOT = {
  suspended: 1291,
  valid:     1046,
  asOf:      "2026-05-21",
};

const PAGE_SIZE = 50;

function SectionHeader({ children, right }) {
  return (
    <div style={{ marginBottom: "16px" }}>
      <div style={{ height: "2px", background: "var(--border-color)", marginBottom: "9px" }} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: "11px",
          fontWeight: 600,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: "var(--text-primary)",
        }}>{children}</span>
        {right && <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: "10px",
          color: "var(--text-muted)",
        }}>{right}</span>}
      </div>
      <div style={{ height: "1px", background: "var(--border-color)", marginTop: "9px" }} />
    </div>
  );
}

function StatusPill({ status }) {
  const p = STATUS_PILLS[status] || STATUS_PILLS.allowed;
  return (
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      gap: "6px",
      padding: "3px 8px 3px 7px",
      background: p.bg,
      border: `1px solid ${p.border}`,
      color: p.fg,
      fontFamily: "var(--font-mono)",
      fontSize: "10px",
      fontWeight: 600,
      letterSpacing: "0.04em",
      textTransform: "uppercase",
      whiteSpace: "nowrap",
    }}>
      <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: p.dot }} />
      {p.label}
    </span>
  );
}

function HeadlineStrip({ summary }) {
  if (!summary) return null;
  const tw = summary.by_direction.tw_imports_from_prc || {};
  const prc = summary.by_direction.prc_imports_from_tw || {};
  const twBanned    = tw.banned || 0;
  const twAllowed   = (tw.ecfa_active || 0) + (tw.conditional || 0);
  const prcSuspended = prc.ecfa_suspended || 0;
  const prcActive    = prc.ecfa_active || 0;
  const prcBanned    = prc.banned || 0;

  return (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid var(--border-color)",
      padding: "16px 18px",
      marginBottom: "16px",
    }}>
      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: "20px",
      }}>
        <div>
          <div style={{
            fontFamily: "var(--font-mono)",
            fontSize: "10px",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: "var(--text-muted)",
            marginBottom: "6px",
          }}>Taiwan as importer</div>
          <div style={{
            fontFamily: "var(--font-serif, Georgia, serif)",
            fontSize: "22px",
            color: "var(--text-primary)",
            lineHeight: 1.25,
          }}>
            <strong style={{ color: "#dc2626" }}>{twBanned.toLocaleString()}</strong> HS lines banned
          </div>
          <div style={{
            fontFamily: "var(--font-body)",
            fontSize: "12px",
            color: "var(--text-secondary)",
            marginTop: "4px",
          }}>
            {twAllowed.toLocaleString()} ECFA-preferred or conditional from PRC
          </div>
        </div>
        <div>
          <div style={{
            fontFamily: "var(--font-mono)",
            fontSize: "10px",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: "var(--text-muted)",
            marginBottom: "6px",
          }}>PRC as importer</div>
          <div style={{
            fontFamily: "var(--font-serif, Georgia, serif)",
            fontSize: "22px",
            color: "var(--text-primary)",
            lineHeight: 1.25,
          }}>
            <strong style={{ color: "#dc2626" }}>{CIFER_SNAPSHOT.suspended.toLocaleString()}</strong> food exporters suspended
          </div>
          <div style={{
            fontFamily: "var(--font-mono)",
            fontSize: "10px",
            color: "var(--text-muted)",
            marginTop: "2px",
          }}>
            GACC CIFER {CIFER_SNAPSHOT.asOf} · {CIFER_SNAPSHOT.valid.toLocaleString()} still valid
          </div>
          <div style={{
            fontFamily: "var(--font-body)",
            fontSize: "12px",
            color: "var(--text-secondary)",
            marginTop: "6px",
          }}>
            ECFA preferences: <strong style={{ color: "#16a34a" }}>{prcActive.toLocaleString()}</strong> active
            <span style={{ color: "var(--text-muted)" }}> · </span>
            <strong style={{ color: "#f59e0b" }}>{prcSuspended}</strong> suspended
            <span style={{ color: "var(--text-muted)" }}> · </span>
            {prcBanned} HS-8 lines targeted (agri/food)
          </div>
        </div>
      </div>
      <p style={{
        marginTop: "14px",
        paddingTop: "12px",
        borderTop: "1px dashed var(--border-color)",
        fontFamily: "var(--font-body)",
        fontSize: "12px",
        color: "var(--text-secondary)",
        lineHeight: 1.5,
      }}>
        The two sides regulate cross-strait imports in fundamentally different ways
        — making the asymmetry as much qualitative as quantitative. Taiwan publishes
        a {twBanned.toLocaleString()}-line HS-8 ban list against PRC-origin goods
        (BOFT 22674), maintained alongside a {(tw.conditional || 0).toLocaleString()}-line
        conditional list. The mainland publishes no equivalent Taiwan-specific
        HS-code ban list — but operates the functional equivalent through
        <strong> GACC exporter facility registration</strong>: all imported food and
        agricultural products must come from a GACC-registered exporter, and
        Beijing suspends those registrations as needed (the "pineapple ban,"
        "grouper ban," etc. are all technically registration suspensions, not
        HS-code bans). As of <strong>2026-05-21</strong>, a direct query of PRC's
        CIFER database (
        <a href="https://ciferquery.singlewindow.cn/" target="_blank" rel="noreferrer"
           style={{ color: "var(--text-secondary)", textDecoration: "underline dotted" }}>
          ciferquery.singlewindow.cn
        </a>
        , 港澳台 tab) found <strong>1,291</strong> Taiwan-registered food
        exporting <em>companies</em> with status <em>暂停进口 (suspended import)</em>{" "}
        against <strong>1,046</strong> still marked <em>有效 (valid)</em> — ~55%
        suspended. These are <em>company-level</em> registrations; each company
        can be registered for multiple products, so the older "~2,000 products
        suspended" figure cited in 2022 reporting referred to a different unit
        and is not directly comparable. Most of these Decree 248 registrations
        carried 5-year terms expiring 2026-01-01; CIFER still surfaces the
        suspended set in that status today rather than as lapsed, suggesting
        the suspensions have hardened into a quasi-permanent state rather than
        being allowed to quietly expire. PRC's CIFER schema also classifies
        Taiwan companies under <em>港澳台</em> (Hong Kong / Macao / Taiwan)
        rather than under <em>境外</em> (foreign) — an administrative
        classification with cross-strait political subtext. The HS-code rows
        below capture what's encoded in published tariff schedules; the
        registration-level dimension is summarised here but not represented
        row-by-row.
      </p>
    </div>
  );
}

function SuspensionTimeline({ waves }) {
  if (!waves?.length) return null;
  return (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid var(--border-color)",
      padding: "14px 18px",
      marginBottom: "20px",
    }}>
      <div style={{
        fontFamily: "var(--font-mono)",
        fontSize: "10px",
        letterSpacing: "0.1em",
        textTransform: "uppercase",
        color: "var(--text-muted)",
        marginBottom: "10px",
      }}>ECFA suspension waves (PRC side)</div>
      <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
        {waves.map((w) => (
          <div key={w.wave} style={{
            flex: "1 1 280px",
            borderLeft: "3px solid #f59e0b",
            paddingLeft: "12px",
          }}>
            <div style={{
              fontFamily: "var(--font-mono)",
              fontSize: "11px",
              fontWeight: 600,
              color: "var(--text-primary)",
            }}>
              Wave {w.wave} · {w.effective}
              <span style={{ color: "var(--text-muted)", fontWeight: 400 }}> · {w.item_count} items</span>
            </div>
            <div style={{
              fontFamily: "var(--font-body)",
              fontSize: "12px",
              color: "var(--text-secondary)",
              marginTop: "4px",
              lineHeight: 1.45,
            }}>
              {w.category}. {w.notes}
            </div>
            <div style={{
              fontFamily: "var(--font-mono)",
              fontSize: "10px",
              color: "var(--text-muted)",
              marginTop: "4px",
            }}>{w.source_label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function FilterBar({ direction, setDirection, status, setStatus, search, setSearch }) {
  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      gap: "10px",
      marginBottom: "16px",
    }}>
      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
        {DIRECTIONS.map((d) => (
          <button
            key={d.id}
            onClick={() => setDirection(d.id === direction ? null : d.id)}
            title={d.blurb}
            style={{
              padding: "6px 14px",
              fontFamily: "var(--font-mono)",
              fontSize: "10px",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              background: direction === d.id ? "var(--text-primary)" : "transparent",
              color: direction === d.id ? "var(--bg-primary)" : "var(--text-secondary)",
              border: "1px solid var(--border-color)",
              cursor: "pointer",
            }}
          >{d.label}</button>
        ))}
      </div>
      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", alignItems: "center" }}>
        {STATUS_FILTERS.map((s) => (
          <button
            key={s.id || "all"}
            onClick={() => setStatus(s.value)}
            style={{
              padding: "4px 10px",
              fontFamily: "var(--font-mono)",
              fontSize: "10px",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              background: status === s.value ? "var(--text-primary)" : "transparent",
              color:      status === s.value ? "var(--bg-primary)"   : "var(--text-secondary)",
              border: "1px solid var(--border-color)",
              cursor: "pointer",
            }}
          >{s.label}</button>
        ))}
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search HS code or product name…"
          style={{
            flex: "1 1 240px",
            minWidth: "200px",
            padding: "6px 10px",
            fontFamily: "var(--font-mono)",
            fontSize: "11px",
            color: "var(--text-primary)",
            background: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            outline: "none",
          }}
        />
      </div>
    </div>
  );
}

function ItemTable({ items, total, page, setPage }) {
  if (!items.length) {
    return (
      <div style={{
        padding: "30px",
        textAlign: "center",
        fontFamily: "var(--font-mono)",
        fontSize: "11px",
        color: "var(--text-muted)",
        background: "var(--bg-card)",
        border: "1px solid var(--border-color)",
      }}>No matching items.</div>
    );
  }
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div>
      <div style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        overflowX: "auto",
      }}>
        <table style={{
          width: "100%",
          borderCollapse: "collapse",
          fontFamily: "var(--font-body)",
          fontSize: "13px",
          color: "var(--text-primary)",
        }}>
          <thead>
            <tr style={{
              borderBottom: "1px solid var(--border-color)",
              background: "var(--bg-primary)",
              fontFamily: "var(--font-mono)",
              fontSize: "10px",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--text-muted)",
            }}>
              <th style={{ textAlign: "left", padding: "8px 12px", whiteSpace: "nowrap" }}>HS code</th>
              <th style={{ textAlign: "left", padding: "8px 12px" }}>中文貨名</th>
              <th style={{ textAlign: "left", padding: "8px 12px" }}>English</th>
              <th style={{ textAlign: "left", padding: "8px 12px", whiteSpace: "nowrap" }}>Status</th>
              <th
                style={{ textAlign: "left", padding: "8px 12px", whiteSpace: "nowrap", cursor: "help" }}
                title="For BOFT rows, the date the current rule code was implemented — the underlying ban may be older if the classification was revised. For ECFA suspensions and curated PRC bans, this is the enforcement date."
              >Last updated</th>
              <th style={{ textAlign: "left", padding: "8px 12px", whiteSpace: "nowrap" }}>Source</th>
            </tr>
          </thead>
          <tbody>
            {items.map((it, i) => (
              <tr key={`${it.direction}-${it.hs_code}-${i}`} style={{
                borderBottom: "1px solid var(--border-color)",
              }}>
                <td style={{
                  padding: "8px 12px",
                  fontFamily: "var(--font-mono)",
                  fontSize: "11px",
                  whiteSpace: "nowrap",
                  color: "var(--text-secondary)",
                }}>{it.hs_code}</td>
                <td style={{ padding: "8px 12px", maxWidth: "260px" }}>{it.product_zh || "—"}</td>
                <td style={{ padding: "8px 12px", color: "var(--text-secondary)", maxWidth: "260px" }}>{it.product_en || "—"}</td>
                <td style={{ padding: "8px 12px" }}><StatusPill status={it.status} /></td>
                <td style={{
                  padding: "8px 12px",
                  fontFamily: "var(--font-mono)",
                  fontSize: "11px",
                  color: "var(--text-muted)",
                  whiteSpace: "nowrap",
                }}>{it.effective_date || "—"}</td>
                <td style={{
                  padding: "8px 12px",
                  fontFamily: "var(--font-mono)",
                  fontSize: "10px",
                  color: "var(--text-muted)",
                  whiteSpace: "nowrap",
                }}>
                  {(() => {
                    // Prefer a per-row announcement URL (curated rows have GACC
                    // notices specific to that ban); fall back to the source-level
                    // dataset / announcement page from SOURCE_URLS.
                    const href = it.ban_announcement_url || SOURCE_URLS[it.source];
                    return href ? (
                      <a href={href} target="_blank" rel="noreferrer" style={{
                        color: "var(--text-muted)", textDecoration: "underline dotted",
                      }}>{it.source}</a>
                    ) : it.source;
                  })()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginTop: "12px",
        fontFamily: "var(--font-mono)",
        fontSize: "10px",
        color: "var(--text-muted)",
      }}>
        <span>
          Showing {items.length} of {total.toLocaleString()} · Page {page + 1} of {totalPages}
        </span>
        <span style={{ display: "flex", gap: "6px" }}>
          <button
            onClick={() => setPage(Math.max(0, page - 1))}
            disabled={page === 0}
            style={{
              padding: "4px 10px",
              fontFamily: "var(--font-mono)",
              fontSize: "10px",
              background: "transparent",
              border: "1px solid var(--border-color)",
              color: page === 0 ? "var(--text-muted)" : "var(--text-primary)",
              cursor: page === 0 ? "default" : "pointer",
              opacity: page === 0 ? 0.4 : 1,
            }}
          >← Prev</button>
          <button
            onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
            disabled={page >= totalPages - 1}
            style={{
              padding: "4px 10px",
              fontFamily: "var(--font-mono)",
              fontSize: "10px",
              background: "transparent",
              border: "1px solid var(--border-color)",
              color: page >= totalPages - 1 ? "var(--text-muted)" : "var(--text-primary)",
              cursor: page >= totalPages - 1 ? "default" : "pointer",
              opacity: page >= totalPages - 1 ? 0.4 : 1,
            }}
          >Next →</button>
        </span>
      </div>
    </div>
  );
}

export default function TradeAccessTab() {
  const [summary, setSummary] = useState(null);
  const [direction, setDirection] = useState(null);  // null = both
  const [status, setStatus] = useState(null);        // null = all
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [data, setData] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);

  // Summary loads once on mount.
  useEffect(() => {
    fetchTradeAccessSummary().then(setSummary).catch(console.error);
  }, []);

  // Debounce the search input so we don't fire on every keystroke.
  useEffect(() => {
    const t = setTimeout(() => { setSearch(searchInput); setPage(0); }, 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  // Reset to first page whenever filters change.
  useEffect(() => { setPage(0); }, [direction, status]);

  // Items query.
  useEffect(() => {
    setLoading(true);
    fetchTradeAccessItems({
      direction,
      status,
      search: search || undefined,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    }).then((d) => {
      setData(d);
      setLoading(false);
    }).catch((e) => {
      console.error(e);
      setLoading(false);
    });
  }, [direction, status, search, page]);

  const lastUpdated = useMemo(() => {
    if (!summary?.last_updated) return "—";
    return summary.last_updated.split(" ")[0];
  }, [summary]);

  return (
    <main style={{ padding: "20px 24px", minWidth: 0 }}>
      <SectionHeader right={`Last refreshed ${lastUpdated}`}>
        Cross-strait trade access
      </SectionHeader>
      <HeadlineStrip summary={summary} />
      <SuspensionTimeline waves={summary?.suspension_waves} />

      <SectionHeader>Browse items</SectionHeader>
      <FilterBar
        direction={direction}
        setDirection={setDirection}
        status={status}
        setStatus={setStatus}
        search={searchInput}
        setSearch={setSearchInput}
      />
      {loading ? (
        <div style={{
          padding: "30px",
          textAlign: "center",
          fontFamily: "var(--font-mono)",
          fontSize: "11px",
          color: "var(--text-muted)",
        }}>Loading…</div>
      ) : (
        <ItemTable items={data.items} total={data.total} page={page} setPage={setPage} />
      )}

      <p style={{
        marginTop: "24px",
        fontFamily: "var(--font-body)",
        fontSize: "11px",
        color: "var(--text-muted)",
        lineHeight: 1.5,
      }}>
        Sources: BOFT (Taiwan Bureau of Foreign Trade) datasets 22674 (不准輸入)
        and 22675 (有條件准許) for Taiwan-side import rules; MoF Customs
        ECFA correspondence table (2024) for the early harvest list; PRC State
        Council Tariff Commission Announcements 2023 No. 9 and 2024 No. 4 for
        ECFA tariff suspension waves; curated list compiled from GACC
        announcements and contemporary news for PRC's targeted agricultural
        and food bans. HS codes are 8-digit, normalised to the importing
        side's tariff schedule.
      </p>
    </main>
  );
}
