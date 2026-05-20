import { useEffect, useMemo, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, Area, ComposedChart,
} from "recharts";
import { fetchEconomySeries, fetchEconomyVerification } from "../api";

// All eight series in the order the API returns them, with display defaults.
// The "headline" indicator (trade balance) is what the sidebar mini shows.
const HEADLINE_SERIES = "trade_balance_usd_b";
const MAIN_CHART_SERIES = "trade_total_usd_b";
const KPI_SERIES = [
  "trade_total_usd_b",
  "trade_balance_usd_b",
  "tw_investment_prc_amount_usd_b",
  "prc_visitors_tw_10k",
];

const RANGE_OPTIONS = [
  { id: "12m", label: "1Y",  months: 12 },
  { id: "36m", label: "3Y",  months: 36 },
  { id: "60m", label: "5Y",  months: 60 },
  { id: "all", label: "All", months: null },
];

function formatPeriodLabel(period) {
  // 'YYYY-MM' → 'MMM YY'
  if (!period) return "";
  const [y, m] = period.split("-");
  const monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${monthNames[Number(m) - 1]} ${y.slice(2)}`;
}

function formatValue(value, unit) {
  if (value === null || value === undefined) return "—";
  if (unit === "USD billions") {
    return `US$${value.toFixed(1)}B`;
  }
  if (unit === "10k persons") {
    // MAC publishes in 萬人; expand to actual persons for display.
    return Math.round(value * 10000).toLocaleString("en-US");
  }
  if (unit === "cases") {
    return Math.round(value).toString();
  }
  return value.toString();
}

function displayUnit(unit) {
  if (unit === "10k persons") return "persons";
  return unit;
}

function formatYAxisTick(value, unit) {
  if (value === null || value === undefined) return "";
  if (unit === "USD billions") return `US$${value}B`;
  if (unit === "10k persons") {
    const actual = value * 10000;
    if (Math.abs(actual) >= 1_000_000) return `${(actual / 1_000_000).toFixed(1)}M`;
    if (Math.abs(actual) >= 1_000) return `${Math.round(actual / 1_000)}K`;
    return actual.toString();
  }
  return value.toString();
}

function formatYoy(yoy) {
  if (yoy === null || yoy === undefined) return null;
  const sign = yoy > 0 ? "+" : "";
  return `${sign}${yoy.toFixed(1)}%`;
}

function YoyChip({ yoy }) {
  if (yoy === null || yoy === undefined) return null;
  const isPositive = yoy > 0;
  const color = isPositive ? "var(--accent-green)" : "var(--accent-red)";
  const arrow = isPositive ? "▲" : "▼";
  return (
    <span style={{
      fontFamily: "var(--font-mono)",
      fontSize: "10px",
      color,
      letterSpacing: "0.04em",
    }}>
      {arrow} {formatYoy(yoy)}
    </span>
  );
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

function KPICard({ series, latest }) {
  if (!series || !latest) return null;
  return (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid var(--border-color)",
      padding: "14px 16px",
      display: "flex",
      flexDirection: "column",
      gap: "6px",
      minWidth: 0,
    }}>
      <span style={{
        fontFamily: "var(--font-mono)",
        fontSize: "9px",
        letterSpacing: "0.12em",
        textTransform: "uppercase",
        color: "var(--text-muted)",
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
      }}>
        {series.label_en}
      </span>
      <span style={{
        fontFamily: "var(--font-headline)",
        fontSize: "26px",
        lineHeight: 1,
        color: "var(--text-primary)",
      }}>
        {formatValue(latest.value, series.unit)}
      </span>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: "9px",
          color: "var(--text-muted)",
          letterSpacing: "0.04em",
        }}>
          {formatPeriodLabel(latest.period)} YoY
        </span>
        <YoyChip yoy={latest.yoy_pct} />
      </div>
    </div>
  );
}

function ChartTooltip({ active, payload, label, unit }) {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload;
  return (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid var(--border-color)",
      padding: "8px 12px",
      fontSize: "11px",
      fontFamily: "var(--font-mono)",
      color: "var(--text-primary)",
    }}>
      <div style={{ color: "var(--text-muted)", marginBottom: "4px" }}>{formatPeriodLabel(label)}</div>
      <div style={{ fontWeight: 600 }}>
        {formatValue(point?.value, unit)}
      </div>
      {point?.yoy_pct !== null && point?.yoy_pct !== undefined && (
        <div style={{ fontSize: "10px", marginTop: "2px" }}>
          YoY <YoyChip yoy={point.yoy_pct} />
        </div>
      )}
    </div>
  );
}

function trimPoints(points, monthsLimit) {
  if (!monthsLimit) return points;
  return points.slice(-monthsLimit);
}

export default function EconomyTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [rangeId, setRangeId] = useState("60m");
  const [pickedSeries, setPickedSeries] = useState("exports_to_prc_usd_b");

  useEffect(() => {
    setLoading(true);
    setLoadError(false);
    fetchEconomySeries()
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch(() => {
        setLoadError(true);
        setLoading(false);
      });
  }, []);

  const seriesById = useMemo(() => {
    if (!data?.series) return {};
    return Object.fromEntries(data.series.map((s) => [s.id, s]));
  }, [data]);

  const monthsLimit = RANGE_OPTIONS.find((r) => r.id === rangeId)?.months;

  const mainSeries = seriesById[MAIN_CHART_SERIES];
  const mainData = mainSeries ? trimPoints(mainSeries.points, monthsLimit) : [];

  const pickedSeriesObj = seriesById[pickedSeries];
  const pickedData = pickedSeriesObj ? trimPoints(pickedSeriesObj.points, monthsLimit) : [];

  if (loadError) {
    return (
      <main style={{ padding: "28px 32px" }}>
        <p style={{
          color: "var(--accent-red)",
          fontFamily: "var(--font-mono)",
          fontSize: "13px",
          padding: "40px 0",
        }}>
          Couldn't load economic data. The API may be unreachable — check the backend
          is running and retry.
        </p>
      </main>
    );
  }

  if (loading || !data) {
    return (
      <main style={{ padding: "28px 32px" }}>
        <p style={{
          color: "var(--text-muted)",
          fontFamily: "var(--font-mono)",
          fontSize: "13px",
          padding: "40px 0",
        }}>
          Loading economic data…
        </p>
      </main>
    );
  }

  return (
    <main style={{ padding: "28px 32px", minWidth: 0, overflow: "hidden", paddingBottom: "40px" }}>
      {/* Intro */}
      <SectionHeader right={data.last_updated ? `MAC · latest ${formatPeriodLabel(data.last_updated)}` : null}>
        Cross-Strait Economy
      </SectionHeader>

      <p style={{
        fontFamily: "var(--font-body)",
        fontSize: "13px",
        color: "var(--text-secondary)",
        marginBottom: "20px",
        lineHeight: 1.5,
      }}>
        Monthly trade, investment and people-flow indicators from Taiwan's Mainland Affairs
        Council (via <em>data.gov.tw</em>). Trade balance is from Taiwan's perspective — positive
        values are TW surplus with PRC.
      </p>

      {/* KPI strip */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
        gap: "10px",
        marginBottom: "32px",
      }}>
        {KPI_SERIES.map((sid) => {
          const s = seriesById[sid];
          if (!s) return null;
          const latest = s.points[s.points.length - 1];
          return <KPICard key={sid} series={s} latest={latest} />;
        })}
      </div>

      {/* Main chart — total trade */}
      <SectionHeader right={
        <span style={{ display: "flex", gap: "6px" }}>
          {RANGE_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              onClick={() => setRangeId(opt.id)}
              style={{
                background: rangeId === opt.id ? "var(--accent-teal)" : "transparent",
                color: rangeId === opt.id ? "#fff" : "var(--text-muted)",
                border: "1px solid var(--border-color)",
                fontFamily: "var(--font-mono)",
                fontSize: "10px",
                letterSpacing: "0.04em",
                padding: "3px 8px",
                cursor: "pointer",
              }}
            >
              {opt.label}
            </button>
          ))}
        </span>
      }>
        {mainSeries?.label_en} (USD billions)
      </SectionHeader>

      <div style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        padding: "16px 12px 8px",
        marginBottom: "32px",
      }}>
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={mainData} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="tradeFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"  stopColor="var(--accent-teal)" stopOpacity={0.18}/>
                <stop offset="100%" stopColor="var(--accent-teal)" stopOpacity={0.0}/>
              </linearGradient>
            </defs>
            <XAxis
              dataKey="period"
              tickFormatter={formatPeriodLabel}
              tick={{ fontSize: 9, fontFamily: "var(--font-mono)", fill: "var(--text-muted)" }}
              axisLine={false}
              tickLine={false}
              minTickGap={28}
            />
            <YAxis
              width={48}
              tick={{ fontSize: 9, fontFamily: "var(--font-mono)", fill: "var(--text-muted)" }}
              tickFormatter={(v) => `US$${v}B`}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip content={(props) => <ChartTooltip {...props} unit={mainSeries?.unit} />} />
            <ReferenceLine y={0} stroke="var(--border-color)" />
            <Area
              type="monotone"
              dataKey="value"
              stroke="none"
              fill="url(#tradeFill)"
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="var(--accent-teal)"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: "var(--accent-teal)" }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Picker chart — flip between indicators */}
      <SectionHeader>
        Explore other indicators
      </SectionHeader>

      <div style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "6px",
        marginBottom: "12px",
      }}>
        {data.series.filter((s) => s.id !== MAIN_CHART_SERIES).map((s) => (
          <button
            key={s.id}
            onClick={() => setPickedSeries(s.id)}
            style={{
              background: pickedSeries === s.id ? "var(--text-primary)" : "transparent",
              color: pickedSeries === s.id ? "var(--bg-primary)" : "var(--text-secondary)",
              border: "1px solid var(--border-color)",
              fontFamily: "var(--font-mono)",
              fontSize: "10px",
              letterSpacing: "0.04em",
              padding: "5px 10px",
              cursor: "pointer",
              whiteSpace: "nowrap",
            }}
          >
            {s.label_en}
          </button>
        ))}
      </div>

      <div style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        padding: "16px 12px 8px",
      }}>
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          padding: "0 4px 8px",
          fontFamily: "var(--font-mono)",
          fontSize: "10px",
          color: "var(--text-muted)",
        }}>
          <span>{pickedSeriesObj?.label_zh}</span>
          <span>{displayUnit(pickedSeriesObj?.unit)}</span>
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={pickedData} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
            <XAxis
              dataKey="period"
              tickFormatter={formatPeriodLabel}
              tick={{ fontSize: 9, fontFamily: "var(--font-mono)", fill: "var(--text-muted)" }}
              axisLine={false}
              tickLine={false}
              minTickGap={28}
            />
            <YAxis
              width={48}
              tick={{ fontSize: 9, fontFamily: "var(--font-mono)", fill: "var(--text-muted)" }}
              tickFormatter={(v) => formatYAxisTick(v, pickedSeriesObj?.unit)}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip content={(props) => <ChartTooltip {...props} unit={pickedSeriesObj?.unit} />} />
            <ReferenceLine y={0} stroke="var(--border-color)" />
            <Line
              type="monotone"
              dataKey="value"
              stroke="var(--accent-amber)"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: "var(--accent-amber)" }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Verification: MAC (TW) vs Comtrade (PRC).
          Uses its own range — PRC data lags MAC by ~6 months so we always
          show a multi-year window to make the overlap visible. */}
      <VerificationSection />

      <p style={{
        fontFamily: "var(--font-mono)",
        fontSize: "10px",
        color: "var(--text-muted)",
        marginTop: "24px",
        lineHeight: 1.5,
      }}>
        Sources: Mainland Affairs Council, R.O.C. (Taiwan) — 兩岸經濟交流統計速報 (dataset
        7887 on <em>data.gov.tw</em>) for cross-strait indicators and 臺灣對香港貿易統計表
        (dataset 7459) for TW-HK trade with HK Census &amp; Statistics Department
        cross-reporting. UN Comtrade preview API (reporter 156 China, partner 490
        "Other Asia, nes") — PRC files Taiwan trade under the "Other Asia" partner code.
        Investment figures count only TW-government-approved cases. People-flow data
        interrupted Jan 2020 – early 2023 due to COVID border controls.
      </p>
    </main>
  );
}

// ---- Verification section ----

// Per-kind presentation: section header, intro paragraph, and the colour for
// the "second reporter" line (TW MAC always uses accent-teal as reporter A).
const VERIFICATION_KINDS = {
  prc_customs: {
    section_label: "Verification — MAC vs PRC Customs",
    reporter_b_color: "var(--accent-red)",
    intro: (
      <>
        Each cross-strait flow as reported by both governments. Solid line: Taiwan's MAC
        (TW customs). Dashed line: PRC's General Administration of Customs (via UN
        Comtrade). The gap typically reflects Hong Kong transit trade booked differently
        by each side, plus methodological differences (e.g. CIF vs FOB valuation).
      </>
    ),
    empty_message: "PRC-reported trade data not yet loaded. Run the Comtrade scraper.",
  },
  hk_customs: {
    section_label: "Verification — MAC vs HK Customs",
    reporter_b_color: "var(--accent-purple)",
    intro: (
      <>
        TW-HK trade as recorded by both customs authorities. Solid line: Taiwan's MAC.
        Dashed line: Hong Kong Census &amp; Statistics Department. The TW→HK leg
        usually agrees within a few percent, but HK records far more outbound trade to
        Taiwan than TW records as imports from HK — most of HK's exports to TW are
        PRC-origin goods that TW books as imports from the mainland instead.
      </>
    ),
    empty_message: "TW-HK trade data not yet loaded. Run scrape_mac_hk_trade.",
  },
};

function VerificationTooltip({ active, payload, label, reporterALabel, reporterBLabel, reporterBColor }) {
  if (!active || !payload?.length) return null;
  const p = payload[0]?.payload || {};
  return (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid var(--border-color)",
      padding: "8px 12px",
      fontSize: "11px",
      fontFamily: "var(--font-mono)",
      color: "var(--text-primary)",
      minWidth: "180px",
    }}>
      <div style={{ color: "var(--text-muted)", marginBottom: "6px" }}>{formatPeriodLabel(label)}</div>
      <div style={{ display: "flex", justifyContent: "space-between", color: "var(--accent-teal)" }}>
        <span>{reporterALabel}</span>
        <span>{p.value_a === null || p.value_a === undefined ? "—" : `US$${p.value_a.toFixed(2)}B`}</span>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", color: reporterBColor }}>
        <span>{reporterBLabel}</span>
        <span>{p.value_b === null || p.value_b === undefined ? "—" : `US$${p.value_b.toFixed(2)}B`}</span>
      </div>
      {p.gap_pct !== null && p.gap_pct !== undefined && (
        <div style={{
          marginTop: "6px",
          paddingTop: "6px",
          borderTop: "1px solid var(--border-color)",
          color: "var(--text-muted)",
          fontSize: "10px",
        }}>
          Δ {p.gap_pct > 0 ? "+" : ""}{p.gap_pct.toFixed(1)}% (B vs A)
        </div>
      )}
    </div>
  );
}

function VerificationFlowChart({ pair, reporterBColor }) {
  const points = pair.points || [];
  const latest = [...points].reverse().find((p) => p.value_a !== null && p.value_b !== null);

  return (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid var(--border-color)",
      padding: "14px 12px 8px",
      marginBottom: "16px",
    }}>
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "baseline",
        padding: "0 4px 10px",
      }}>
        <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: "11px",
          fontWeight: 600,
          color: "var(--text-primary)",
          letterSpacing: "0.04em",
        }}>
          {pair.label_en}
        </span>
        {latest && (
          <span style={{
            fontFamily: "var(--font-mono)",
            fontSize: "10px",
            color: "var(--text-muted)",
          }}>
            {formatPeriodLabel(latest.period)}: {pair.reporter_a_label} <span style={{ color: "var(--accent-teal)" }}>US${latest.value_a.toFixed(2)}B</span>
            {" · "}{pair.reporter_b_label} <span style={{ color: reporterBColor }}>US${latest.value_b.toFixed(2)}B</span>
            {latest.gap_pct !== null && latest.gap_pct !== undefined && (
              <span style={{ color: latest.gap_pct >= 0 ? "var(--accent-amber)" : "var(--accent-purple)", marginLeft: "8px" }}>
                Δ {latest.gap_pct > 0 ? "+" : ""}{latest.gap_pct.toFixed(1)}%
              </span>
            )}
          </span>
        )}
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={points} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
          <XAxis
            dataKey="period"
            tickFormatter={formatPeriodLabel}
            tick={{ fontSize: 9, fontFamily: "var(--font-mono)", fill: "var(--text-muted)" }}
            axisLine={false}
            tickLine={false}
            minTickGap={28}
          />
          <YAxis
            width={48}
            tick={{ fontSize: 9, fontFamily: "var(--font-mono)", fill: "var(--text-muted)" }}
            tickFormatter={(v) => `US$${v}`}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            content={
              <VerificationTooltip
                reporterALabel={pair.reporter_a_label}
                reporterBLabel={pair.reporter_b_label}
                reporterBColor={reporterBColor}
              />
            }
          />
          <Line
            type="monotone"
            dataKey="value_a"
            name={pair.reporter_a_label}
            stroke="var(--accent-teal)"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: "var(--accent-teal)" }}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="value_b"
            name={pair.reporter_b_label}
            stroke={reporterBColor}
            strokeWidth={2}
            strokeDasharray="4 3"
            dot={false}
            activeDot={{ r: 4, fill: reporterBColor }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

const VERIFICATION_DEFAULT_MONTHS = 60;

function VerificationKindSubsection({ kind, pairs }) {
  const cfg = VERIFICATION_KINDS[kind];
  if (!cfg) return null;
  const hasData = pairs.some((p) => p.points.some((pt) => pt.value_b !== null));
  return (
    <>
      <SectionHeader>{cfg.section_label}</SectionHeader>
      <p style={{
        fontFamily: "var(--font-body)",
        fontSize: "12px",
        color: "var(--text-secondary)",
        marginBottom: "14px",
        lineHeight: 1.5,
      }}>
        {cfg.intro}
      </p>
      {hasData ? (
        pairs.map((pair) => (
          <VerificationFlowChart
            key={pair.flow_id}
            pair={pair}
            reporterBColor={cfg.reporter_b_color}
          />
        ))
      ) : (
        <p style={{
          fontFamily: "var(--font-mono)", fontSize: "11px",
          color: "var(--text-muted)", padding: "12px 0 24px",
        }}>
          {cfg.empty_message}
        </p>
      )}
    </>
  );
}

function VerificationSection() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchEconomyVerification({ months: VERIFICATION_DEFAULT_MONTHS })
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <>
        <SectionHeader>Verification — Cross-strait trade by reporter</SectionHeader>
        <p style={{
          fontFamily: "var(--font-mono)", fontSize: "11px",
          color: "var(--text-muted)", padding: "20px 0",
        }}>Loading verification data…</p>
      </>
    );
  }

  if (!data?.pairs?.length) return null;

  // Group pairs by kind, preserving the API's declared order
  const groupedKinds = [];
  const seen = new Set();
  for (const pair of data.pairs) {
    if (!seen.has(pair.kind)) {
      seen.add(pair.kind);
      groupedKinds.push(pair.kind);
    }
  }
  const byKind = Object.fromEntries(
    groupedKinds.map((k) => [k, data.pairs.filter((p) => p.kind === k)])
  );

  return (
    <>
      {groupedKinds.map((kind) => (
        <VerificationKindSubsection key={kind} kind={kind} pairs={byKind[kind]} />
      ))}
    </>
  );
}

// Tiny sidebar widget — exported separately so StatsSidebar can consume it.
export function EconomyMini({ onOpen }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetchEconomySeries({ ids: [HEADLINE_SERIES, "trade_total_usd_b"].join(","), months: 13 })
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data?.series?.length) return null;
  const balance = data.series.find((s) => s.id === HEADLINE_SERIES);
  const total = data.series.find((s) => s.id === "trade_total_usd_b");
  if (!balance?.points?.length || !total?.points?.length) return null;
  const balanceLatest = balance.points[balance.points.length - 1];
  const totalLatest = total.points[total.points.length - 1];

  return (
    <div style={{ marginBottom: "28px" }}>
      <div style={{ marginBottom: "12px" }}>
        <div style={{ height: "2px", background: "var(--border-color)", marginBottom: "8px" }} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={{
            fontFamily: "var(--font-mono)",
            fontSize: "10px",
            fontWeight: 600,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: "var(--text-primary)",
          }}>
            Cross-Strait Economy
          </span>
          <button
            onClick={onOpen}
            style={{
              background: "transparent",
              border: "none",
              fontFamily: "var(--font-mono)",
              fontSize: "9px",
              color: "var(--text-muted)",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              cursor: "pointer",
              padding: 0,
            }}
            title="Open Economy tab"
          >
            More →
          </button>
        </div>
      </div>

      <button
        onClick={onOpen}
        style={{
          width: "100%",
          background: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          padding: "12px 14px",
          cursor: "pointer",
          textAlign: "left",
          display: "flex",
          flexDirection: "column",
          gap: "10px",
        }}
      >
        {/* Trade balance with PRC — headline */}
        <div>
          <div style={{
            fontFamily: "var(--font-mono)",
            fontSize: "9px",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: "var(--text-muted)",
          }}>
            TW–PRC trade balance · {formatPeriodLabel(balanceLatest.period)}
          </div>
          <div style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            marginTop: "2px",
          }}>
            <span style={{
              fontFamily: "var(--font-headline)",
              fontSize: "22px",
              color: "var(--text-primary)",
              lineHeight: 1,
            }}>
              {formatValue(balanceLatest.value, balance.unit)}
            </span>
            <YoyChip yoy={balanceLatest.yoy_pct} />
          </div>
          <div style={{
            fontFamily: "var(--font-mono)",
            fontSize: "9px",
            color: "var(--text-muted)",
            marginTop: "3px",
            fontStyle: "italic",
          }}>
            {balanceLatest.value >= 0 ? "TW surplus" : "TW deficit"} with mainland China
          </div>
        </div>

        {/* Total bilateral trade — subline */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={{
            fontFamily: "var(--font-mono)",
            fontSize: "10px",
            color: "var(--text-secondary)",
          }}>
            Bilateral trade {formatValue(totalLatest.value, total.unit)}
          </span>
          <YoyChip yoy={totalLatest.yoy_pct} />
        </div>
      </button>
    </div>
  );
}
