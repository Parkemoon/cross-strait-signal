import { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  BarChart, Bar, CartesianGrid, ReferenceLine,
} from "recharts";
import { fetchPeopleRecords } from "../api";

const POLICY_DOT_COLOR = "var(--accent-amber)";

// formatLargeNumber keeps one decimal up to 100M so 11.6M renders as
// "11.6M" rather than rounding to "12M". The economy tab's version
// switched to integer Ms at 10M+; we explicitly don't do that here
// because the 台胞证 cumulative figure (11.6M) and the policy timeline's
// "12M+ targeted residents" number (~TW pop minus the 11.6M holders)
// are different concepts and should be visibly different.
function formatLargeNumber(n) {
  if (n === null || n === undefined) return "—";
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(n >= 1e5 ? 0 : 1)}K`;
  return n.toLocaleString();
}

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

function PeopleKPICard({ value, label, sublabel, footnote }) {
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
      }}>{label}</div>
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
      {footnote && (
        <div style={{
          fontFamily: "var(--font-mono)",
          fontSize: "9.5px",
          color: "var(--text-muted)",
          marginTop: "6px",
        }}>{footnote}</div>
      )}
    </div>
  );
}

function PeoplePermitsChart({ residence, settlement }) {
  const byPeriod = {};
  for (const r of residence || []) byPeriod[r.period] = { period: r.period, residence: r.value };
  for (const r of settlement || []) byPeriod[r.period] = { ...byPeriod[r.period], period: r.period, settlement: r.value };
  const data = Object.values(byPeriod).sort((a, b) => a.period.localeCompare(b.period));

  return (
    <div style={{ height: "240px", marginTop: "8px" }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 4, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="var(--border-color)" />
          <XAxis
            dataKey="period"
            tick={{ fontFamily: "var(--font-mono)", fontSize: 10, fill: "var(--text-muted)" }}
            stroke="var(--border-color)"
          />
          <YAxis
            tick={{ fontFamily: "var(--font-mono)", fontSize: 10, fill: "var(--text-muted)" }}
            stroke="var(--border-color)"
            tickFormatter={(v) => formatLargeNumber(v)}
          />
          <Tooltip
            contentStyle={{
              background: "var(--bg-primary)",
              border: "1px solid var(--border-color)",
              fontFamily: "var(--font-mono)",
              fontSize: "11px",
            }}
            formatter={(v, key) => [
              v.toLocaleString(),
              key === "residence" ? "Residence (居留)" : "Settlement (定居)",
            ]}
          />
          <Bar dataKey="residence" fill="var(--accent-teal, #14B8A6)" />
          <Bar dataKey="settlement" fill="var(--text-primary)" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// Long-history annual view — pulled from Tourism Bureau (stat.taiwan.net.tw).
// Covers 2008→ which pre-dates MAC 7887's 2017-08 archive window. We keep the
// PRC visitor line dashed-placeholder until a matching prc_inbound_annual is
// curated; for now, only TW outbound is plotted.
function AnnualFlowChart({ tw, prc }) {
  const byYear = {};
  for (const r of tw?.series || []) byYear[r.year] = { year: r.year, tw: r.visitors };
  for (const r of prc?.series || []) byYear[r.year] = { ...byYear[r.year], year: r.year, prc: r.visitors };
  const data = Object.values(byYear).sort((a, b) => a.year - b.year);

  return (
    <div style={{ height: "220px", marginTop: "8px" }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 12, right: 12, left: 4, bottom: 8 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="var(--border-color)" />
          <XAxis
            dataKey="year"
            tick={{ fontFamily: "var(--font-mono)", fontSize: 10, fill: "var(--text-muted)" }}
            stroke="var(--border-color)"
            interval="preserveStartEnd"
            minTickGap={28}
          />
          <YAxis
            tick={{ fontFamily: "var(--font-mono)", fontSize: 10, fill: "var(--text-muted)" }}
            stroke="var(--border-color)"
            tickFormatter={(v) => (v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${Math.round(v / 1e3)}K` : v)}
          />
          <Tooltip
            contentStyle={{
              background: "var(--bg-primary)",
              border: "1px solid var(--border-color)",
              fontFamily: "var(--font-mono)",
              fontSize: "11px",
            }}
            formatter={(v, key) => [
              v !== null && v !== undefined ? v.toLocaleString() + " visitors" : "—",
              key === "tw" ? "TW → PRC" : "PRC → TW",
            ]}
            labelFormatter={(y) => `Year ${y}`}
          />
          {prc?.series?.length > 0 && (
            <Line type="monotone" dataKey="prc" stroke="var(--accent-teal, #14B8A6)"
                  strokeWidth={1.5} dot={{ r: 2, fill: "var(--accent-teal, #14B8A6)" }}
                  activeDot={{ r: 4 }} />
          )}
          <Line type="monotone" dataKey="tw" stroke="var(--text-primary)"
                strokeWidth={1.5} dot={{ r: 2, fill: "var(--text-primary)" }}
                activeDot={{ r: 4 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

const MONTH_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

// "2024-03" → "Mar '24"
function fmtMonthYear(period) {
  if (!period) return "";
  const [y, m] = period.split("-");
  return `${MONTH_ABBR[Number(m) - 1]} '${y.slice(2)}`;
}

// MAC 7887 only publishes the TW→PRC outbound visitor figure from 2024-03
// onwards (the column existed earlier but was '－' for years). Show all
// available data rather than slicing to a fixed window — slicing made the
// TW line look like it cliffed out of nowhere. Visible dots on each data
// point make the actual reporting cadence legible (MAC skips an occasional
// month for tw_visitors_prc; prc_visitors_tw is unbroken monthly).
function PeopleFlowChart({ tw, prc }) {
  const byPeriod = {};
  for (const r of prc?.series || []) byPeriod[r.period] = { period: r.period, prc: r.value };
  for (const r of tw?.series || []) {
    byPeriod[r.period] = { ...byPeriod[r.period], period: r.period, tw: r.value };
  }
  const data = Object.values(byPeriod).sort((a, b) => a.period.localeCompare(b.period));

  // Mark the first period where TW outbound data exists so readers can
  // see "this isn't a cliff — MAC just started publishing here."
  const twDebut = (tw?.series || []).find((r) => r.value !== null && r.value !== undefined)?.period;

  return (
    <div style={{ height: "240px", marginTop: "8px" }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="var(--border-color)" />
          <XAxis
            dataKey="period"
            tick={{ fontFamily: "var(--font-mono)", fontSize: 10, fill: "var(--text-muted)" }}
            stroke="var(--border-color)"
            tickFormatter={fmtMonthYear}
            interval="preserveStartEnd"
            minTickGap={48}
          />
          <YAxis
            tick={{ fontFamily: "var(--font-mono)", fontSize: 10, fill: "var(--text-muted)" }}
            stroke="var(--border-color)"
            tickFormatter={(v) => `${v}`}
          />
          <Tooltip
            labelFormatter={fmtMonthYear}
            contentStyle={{
              background: "var(--bg-primary)",
              border: "1px solid var(--border-color)",
              fontFamily: "var(--font-mono)",
              fontSize: "11px",
            }}
            formatter={(v, key) => [
              v !== null && v !== undefined ? `${(v * 10000).toLocaleString()} persons` : "—",
              key === "tw" ? "TW → PRC" : "PRC → TW",
            ]}
          />
          {twDebut && (
            <ReferenceLine
              x={twDebut}
              stroke="var(--text-muted)"
              strokeDasharray="3 3"
              label={{
                value: "MAC begins TW outbound",
                position: "insideTopRight",
                fill: "var(--text-muted)",
                fontSize: 9,
                fontFamily: "var(--font-mono)",
              }}
            />
          )}
          <Line
            type="monotone"
            dataKey="prc"
            stroke="var(--accent-teal, #14B8A6)"
            strokeWidth={1.5}
            dot={{ r: 1.6, fill: "var(--accent-teal, #14B8A6)", strokeWidth: 0 }}
            activeDot={{ r: 4 }}
          />
          <Line
            type="monotone"
            dataKey="tw"
            stroke="var(--text-primary)"
            strokeWidth={1.5}
            dot={{ r: 1.8, fill: "var(--text-primary)", strokeWidth: 0 }}
            activeDot={{ r: 4 }}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function PeopleTab() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetchPeopleRecords()
      .then(setData)
      .catch(() => setError(true));
  }, []);

  if (error) {
    return (
      <main style={{ padding: "28px 32px" }}>
        <p style={{ color: "var(--accent-red)", fontFamily: "var(--font-mono)", fontSize: "13px", padding: "40px 0" }}>
          Couldn't load people-records.
        </p>
      </main>
    );
  }
  if (!data) {
    return (
      <main style={{ padding: "28px 32px" }}>
        <p style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: "13px", padding: "40px 0" }}>
          Loading people records…
        </p>
      </main>
    );
  }

  const prcInTw = data.directions?.prc_in_taiwan || {};
  const twInPrc = data.directions?.taiwanese_in_prc || {};
  const census = (twInPrc.census_residents || [])[0];
  const tbzPermits = (twInPrc.tbz_cumulative_permits || [])[0];
  const tbzHolders = (twInPrc.tbz_cumulative_holders || [])[0];
  const tbzAnnualPartial = (twInPrc.tbz_annual_issued_partial || [])[0];
  const latestResidence = (prcInTw.permits_annual_residence || []).slice(-1)[0];
  const spousesLatest = (prcInTw.spouses_cumulative || []).slice(-1)[0];
  const sources = data.meta?.refresh_cadence;

  return (
    <main style={{ padding: "28px 32px", minWidth: 0, overflow: "hidden", paddingBottom: "40px" }}>
      <SectionHeader right={data.meta?.extracted_at ? `latest curated ${data.meta.extracted_at}` : null}>
        Cross-Strait People &amp; Movement
      </SectionHeader>

      <p style={{
        fontFamily: "var(--font-body)",
        fontSize: "13px",
        color: "var(--text-secondary)",
        marginBottom: "20px",
        lineHeight: 1.55,
      }}>
        How many people live on the other side of the strait, and how many cross it each month.
        PRC residents in Taiwan are tracked by Taiwan's NIA via residence and settlement permits;
        Taiwanese in PRC are only knowable through PRC bureaus — 台胞证 issuance counts, the 2020
        census, and occasional NIA press releases. Stock first, flow below.
      </p>

      {/* Headline KPI strip */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
        gap: "10px",
        marginBottom: "28px",
      }}>
        {tbzHolders && (
          <PeopleKPICard
            value={formatLargeNumber(tbzHolders.value)}
            label="台胞证 holders (cumulative)"
            sublabel="Unique Taiwanese with mainland entry permits"
            footnote={`PRC公安部, as of ${tbzHolders.period}`}
          />
        )}
        {census && (
          <PeopleKPICard
            value={census.value.toLocaleString()}
            label="Taiwanese resident in PRC"
            sublabel="2020 PRC Census enumeration"
            footnote="No comparable TW-side birthplace figure (see note below)"
          />
        )}
        {spousesLatest && (
          <PeopleKPICard
            value={formatLargeNumber(spousesLatest.value)}
            label="Mainland spouses in Taiwan"
            sublabel="Cumulative since 1987"
            footnote={`TW NIA, as of ${spousesLatest.period}`}
          />
        )}
        {latestResidence && (
          <PeopleKPICard
            value={latestResidence.value.toLocaleString()}
            label="New PRC residence permits"
            sublabel="Annual flow, latest TW NIA year"
            footnote={`${latestResidence.period} — bouncing back post-COVID`}
          />
        )}
      </div>

      {/* Bidirectional 2-column. Collapses to 1 column below ~680px. */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))",
        gap: "20px",
        marginBottom: "24px",
      }}>
        {/* LEFT — PRC residents in Taiwan */}
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
            marginBottom: "4px",
          }}>PRC → Taiwan</div>
          <h3 style={{
            fontFamily: "var(--font-display)",
            fontSize: "16px",
            fontWeight: 500,
            color: "var(--text-primary)",
            margin: 0,
          }}>New residence &amp; settlement permits</h3>
          <p style={{
            fontFamily: "var(--font-body)",
            fontSize: "11.5px",
            color: "var(--text-secondary)",
            marginTop: "4px",
            marginBottom: "0",
            lineHeight: 1.45,
          }}>
            居留 (residence, teal) is the first-stage permit; 定居 (settlement, dark)
            is the second-stage permit toward permanent residency. Both collapsed
            during 2020–2022 (border closure) and rebounded in 2023.
          </p>
          <PeoplePermitsChart
            residence={prcInTw.permits_annual_residence}
            settlement={prcInTw.permits_annual_settlement}
          />
          <p style={{
            fontFamily: "var(--font-mono)",
            fontSize: "9.5px",
            color: "var(--text-muted)",
            marginTop: "4px",
          }}>TW NIA 167829 · {(prcInTw.permits_annual_residence || []).length} years</p>
        </div>

        {/* RIGHT — Taiwanese in PRC: milestones + policy timeline */}
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
            marginBottom: "4px",
          }}>Taiwan → PRC</div>
          <h3 style={{
            fontFamily: "var(--font-display)",
            fontSize: "16px",
            fontWeight: 500,
            color: "var(--text-primary)",
            margin: 0,
          }}>台胞证 milestones &amp; regime changes</h3>
          <p style={{
            fontFamily: "var(--font-body)",
            fontSize: "11.5px",
            color: "var(--text-secondary)",
            marginTop: "4px",
            marginBottom: "10px",
            lineHeight: 1.45,
          }}>
            PRC bureaus publish absolute counts only at irregular intervals.
            The cliff in 2020–2022 (border closure) reset the flow; 2024 partial
            issuance suggests recovery is underway.
          </p>

          <div style={{ display: "grid", gap: "8px", marginBottom: "16px" }}>
            {tbzPermits && (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "10px" }}>
                <span style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--text-secondary)" }}>
                  Cumulative 台胞证 permits ({tbzPermits.period})
                </span>
                <span style={{ fontFamily: "var(--font-display)", fontSize: "15px", color: "var(--text-primary)" }}>
                  {formatLargeNumber(tbzPermits.value)}
                </span>
              </div>
            )}
            {tbzAnnualPartial && (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "10px" }}>
                <span style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--text-secondary)" }}>
                  Permits issued {tbzAnnualPartial.period} <em style={{ color: "var(--text-muted)" }}>(Q1–Q3)</em>
                </span>
                <span style={{ fontFamily: "var(--font-display)", fontSize: "15px", color: "var(--text-primary)" }}>
                  {formatLargeNumber(tbzAnnualPartial.value)}
                </span>
              </div>
            )}
          </div>

          <div style={{
            fontFamily: "var(--font-mono)",
            fontSize: "10px",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: "var(--text-muted)",
            marginBottom: "8px",
          }}>Regulatory timeline</div>
          <ol style={{
            listStyle: "none",
            padding: 0,
            margin: 0,
            borderLeft: "1px solid var(--border-color)",
          }}>
            {(data.policy_timeline || []).map((ev, i) => (
              <li key={i} style={{
                position: "relative",
                paddingLeft: "16px",
                paddingBottom: "10px",
                marginLeft: "4px",
              }}>
                <span style={{
                  position: "absolute",
                  left: "-5px",
                  top: "4px",
                  width: "8px",
                  height: "8px",
                  borderRadius: "50%",
                  background: POLICY_DOT_COLOR,
                }} />
                <div style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "10px",
                  color: "var(--text-muted)",
                  marginBottom: "2px",
                }}>{ev.date}</div>
                <div style={{
                  fontFamily: "var(--font-body)",
                  fontSize: "12px",
                  color: "var(--text-primary)",
                  fontWeight: 500,
                  lineHeight: 1.3,
                }}>{ev.event}</div>
                {ev.blurb && (
                  <div style={{
                    fontFamily: "var(--font-body)",
                    fontSize: "11px",
                    color: "var(--text-secondary)",
                    marginTop: "3px",
                    lineHeight: 1.4,
                  }}>{ev.blurb}</div>
                )}
              </li>
            ))}
          </ol>
        </div>
      </div>

      {/* Annual flow strip — long-history Tourism Bureau context.
          Sits above the monthly chart so the multi-decade trend (COVID
          cliff and pre-2019 ~4M peak) frames the recent monthly cadence. */}
      {data.annual_flows?.tw_to_prc?.series?.length > 0 && (
        <div style={{
          padding: "14px 16px",
          border: "1px solid var(--border-color)",
          background: "var(--bg-card)",
          marginBottom: "16px",
        }}>
          <div style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            gap: "10px",
            marginBottom: "4px",
          }}>
            <h3 style={{
              fontFamily: "var(--font-display)",
              fontSize: "15px",
              fontWeight: 500,
              color: "var(--text-primary)",
              margin: 0,
            }}>Annual visitor flows — long view</h3>
            <span style={{
              fontFamily: "var(--font-mono)",
              fontSize: "9.5px",
              color: "var(--text-muted)",
            }}>觀光署 · persons / year</span>
          </div>
          <p style={{
            fontFamily: "var(--font-body)",
            fontSize: "11.5px",
            color: "var(--text-secondary)",
            marginTop: "4px",
            marginBottom: "0",
            lineHeight: 1.45,
          }}>
            Series begins 2008 because direct cross-strait flights opened that December
            (大三通) — before then, travel had to route via Hong Kong, Macao, or third
            countries, so a "TW→PRC visitors" annual count isn't meaningfully distinct
            from outbound travel generally.{" "}
            <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>TW → PRC</span>{" "}
            peaked at ~4.17M in 2018, collapsed to ~130K under COVID (2021), recovery to
            ~3.24M by 2025 — back to ~78% of the 2018 high.{" "}
            <span style={{ color: "var(--accent-teal, #14B8A6)", fontWeight: 600 }}>PRC → TW</span>{" "}
            peaked earlier (~4.14M in 2015), declined under the 2019 自由行 ban, hit
            ~13K in 2021, and has only rebuilt to ~620K — 15% of the 2015 high. The
            asymmetric recovery is the analytical story. Both lines from 觀光署; PRC→TW
            uses the 華僑 column under 居住地=中國大陸. 華僑 is an umbrella status
            category by definition, but cross-checked against MAC 7887 it matches
            within rounding — the umbrella's edge cases (港澳 / 無戶籍國民 with
            residence in mainland) are negligible in practice.
          </p>
          <AnnualFlowChart
            tw={data.annual_flows?.tw_to_prc}
            prc={data.annual_flows?.prc_to_tw}
          />
        </div>
      )}

      {/* Flow strip — paired monthly visitors */}
      <div style={{
        padding: "14px 16px",
        border: "1px solid var(--border-color)",
        background: "var(--bg-card)",
        marginBottom: "24px",
      }}>
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          gap: "10px",
          marginBottom: "4px",
        }}>
          <h3 style={{
            fontFamily: "var(--font-display)",
            fontSize: "15px",
            fontWeight: 500,
            color: "var(--text-primary)",
            margin: 0,
          }}>Monthly visitor flows</h3>
          <span style={{
            fontFamily: "var(--font-mono)",
            fontSize: "9.5px",
            color: "var(--text-muted)",
          }}>MAC 7887 · 10k persons</span>
        </div>
        <p style={{
          fontFamily: "var(--font-body)",
          fontSize: "11.5px",
          color: "var(--text-secondary)",
          marginTop: "4px",
          marginBottom: "0",
          lineHeight: 1.45,
        }}>
          <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>TW → PRC</span>{" "}
          (dark) and{" "}
          <span style={{ color: "var(--accent-teal, #14B8A6)", fontWeight: 600 }}>PRC → TW</span>{" "}
          (teal). Dots show each MAC release. The PRC→TW line is monthly across 2017→
          (pre-2019 ~250K/month, COVID floor near zero 2020–22, recovery still
          incomplete). MAC only started carrying TW outbound in dataset 7887 in March
          2024 (marked) and skips an occasional month — for the pre-2024 TW trend, see
          the annual chart above.
        </p>
        <PeopleFlowChart tw={data.flows?.tw_visitors_to_prc} prc={data.flows?.prc_visitors_to_tw} />
      </div>

      {/* Methodology note — why the two sides are measured differently */}
      <div style={{
        padding: "14px 16px",
        border: "1px dashed var(--border-color)",
        background: "transparent",
        marginBottom: "16px",
      }}>
        <div style={{
          fontFamily: "var(--font-mono)",
          fontSize: "10px",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "var(--text-muted)",
          marginBottom: "8px",
        }}>Why the two sides aren't symmetric</div>
        <p style={{
          fontFamily: "var(--font-body)",
          fontSize: "12px",
          color: "var(--text-secondary)",
          margin: 0,
          lineHeight: 1.55,
        }}>
          ROC household registration dropped the 籍貫 (ancestral home) field in 1992 to
          dissolve 省籍情結, and DGBAS's modern census doesn't publish a 出生地 (place of
          birth) cross-tab — the 109 census variables are population, age, sex,
          households, residences, and indigenous status only. That means the 1949-era 外省
          人 cohort and naturalised mainland spouses are statistically invisible from the
          TW side. We approximate "PRC presence in TW" via NIA permits and the 大陸配偶
          cumulative stock. On the PRC side, the 2020 census Bulletin No.8 does report
          Taiwanese registered as 常住人口 (157,886) — the only directly comparable
          stock figure.
        </p>
      </div>

      <p style={{
        fontFamily: "var(--font-mono)",
        fontSize: "9.5px",
        color: "var(--text-muted)",
        marginTop: "10px",
        lineHeight: 1.5,
      }}>
        Sources: TW NIA datasets 167829 (居留/定居 permits) and 13503 (大陸/港澳配偶) via
        opdadm.moi.gov.tw; PRC公安部 / 國家移民管理局 press releases (curated milestones);
        2020 PRC Census Bulletin No.8; MAC dataset 7887 for monthly visitor flows. Refresh: {sources || "annual"}.
      </p>
    </main>
  );
}
