import { useEffect, useMemo, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, Area, ComposedChart, BarChart, Bar, CartesianGrid,
} from "recharts";
import {
  fetchEconomySeries, fetchEconomyVerification, fetchInvestmentByIndustry,
  fetchInvestmentVerification, fetchPeopleRecords,
} from "../api";

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

// TW vs PRC macro side-by-side. Each pair gets its own chart in the Macro
// section. `dualAxis` is true when the two scales are very different
// (TW FX ~$600B vs PRC ~$3.3T; TWD/USD ~31 vs CNY/USD ~7).
const MACRO_PAIRS = [
  { id: "gdp_growth", tw: "tw_gdp_growth_pct",    prc: "prc_gdp_growth_pct",
    title: "Real GDP growth (YoY)", dualAxis: false },
  { id: "cpi",        tw: "tw_cpi_yoy_pct",       prc: "prc_cpi_yoy_pct",
    title: "Consumer prices (YoY)", dualAxis: false },
  { id: "fx_res",     tw: "tw_fx_reserves_usd_b", prc: "prc_fx_reserves_usd_b",
    title: "Foreign exchange reserves", dualAxis: true },
  { id: "fx_rate",    tw: "twd_usd_rate",         prc: "cny_usd_rate",
    title: "Exchange rate vs USD", dualAxis: true },
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
  if (unit === "percent") {
    return `${value.toFixed(2)}%`;
  }
  if (unit === "rate") {
    return value.toFixed(3);
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
  if (unit === "percent") return `${value}%`;
  if (unit === "rate") return value.toString();
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
        {data.series
          .filter((s) => s.id !== MAIN_CHART_SERIES && s.category !== "macro")
          .map((s) => (
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

      {/* Cross-strait investment by industry (MAC 7478 + 7473), with
          direction toggle to expose the ~50× asymmetry between flows. */}
      <InvestmentSection />

      {/* Cross-strait people: who lives on the other side, plus visitor
          flow context. TW NIA permits + curated PRC-side milestones. */}
      <PeopleSection />

      {/* Macro: TW vs PRC side-by-side (MAC dataset 7888). */}
      <MacroSection seriesById={seriesById} monthsLimit={monthsLimit} />

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
        7887) for cross-strait indicators, 臺灣對香港貿易統計表 (7459) for TW-HK trade
        with HK Census &amp; Statistics Department cross-reporting, and 兩岸重要經濟指標
        統計速報 (7888) for TW vs PRC macro indicators — all via <em>data.gov.tw</em>.
        UN Comtrade preview API (reporter 156 China, partner 490 "Other Asia, nes") —
        PRC files Taiwan trade under the "Other Asia" partner code. Investment figures
        count only TW-government-approved cases. People-flow data interrupted Jan 2020 –
        early 2023 due to COVID border controls. GDP is quarterly; other indicators
        monthly.
      </p>
    </main>
  );
}

// ---- Macro section (TW vs PRC) ----

function MacroPairTooltip({ active, payload, label, twLabel, prcLabel, unit }) {
  if (!active || !payload?.length) return null;
  // Recharts gives us one payload entry per Line; we surface both reporters.
  const tw = payload.find((p) => p.dataKey === "tw_value");
  const prc = payload.find((p) => p.dataKey === "prc_value");
  const fmt = (v) => {
    if (v === null || v === undefined) return "—";
    if (unit === "percent") return `${v.toFixed(2)}%`;
    if (unit === "rate") return v.toFixed(3);
    if (unit === "USD billions") return `US$${v.toFixed(1)}B`;
    return v.toString();
  };
  return (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid var(--border-color)",
      padding: "8px 12px",
      fontSize: "11px",
      fontFamily: "var(--font-mono)",
      color: "var(--text-primary)",
      minWidth: "160px",
    }}>
      <div style={{ color: "var(--text-muted)", marginBottom: "6px" }}>{formatPeriodLabel(label)}</div>
      <div style={{ display: "flex", justifyContent: "space-between", color: "var(--accent-teal)" }}>
        <span>{twLabel}</span>
        <span>{fmt(tw?.value)}</span>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", color: "var(--accent-red)" }}>
        <span>{prcLabel}</span>
        <span>{fmt(prc?.value)}</span>
      </div>
    </div>
  );
}

// Merge two series (TW and PRC) into a single array of {period, tw_value, prc_value}
// keyed by the union of periods, so Recharts can plot them on a shared time axis.
function mergePair(twPoints, prcPoints) {
  const map = new Map();
  for (const p of twPoints || []) {
    map.set(p.period, { period: p.period, tw_value: p.value, prc_value: null });
  }
  for (const p of prcPoints || []) {
    const existing = map.get(p.period) || { period: p.period, tw_value: null };
    existing.prc_value = p.value;
    map.set(p.period, existing);
  }
  return Array.from(map.values()).sort((a, b) => a.period.localeCompare(b.period));
}

function MacroPairChart({ pair, seriesById, monthsLimit }) {
  const twSeries = seriesById[pair.tw];
  const prcSeries = seriesById[pair.prc];
  if (!twSeries || !prcSeries) return null;

  const twPoints = trimPoints(twSeries.points, monthsLimit);
  const prcPoints = trimPoints(prcSeries.points, monthsLimit);
  const merged = mergePair(twPoints, prcPoints);
  if (!merged.length) return null;

  const unit = twSeries.unit;
  const latestPeriod = merged[merged.length - 1].period;
  const latestTw = [...merged].reverse().find((p) => p.tw_value !== null)?.tw_value;
  const latestPrc = [...merged].reverse().find((p) => p.prc_value !== null)?.prc_value;

  const formatTick = (v) => formatYAxisTick(v, unit);
  // For exchange rates the suffix is the currency; for percent the suffix is %; etc.
  const formatLatest = (v) => {
    if (v === null || v === undefined) return "—";
    if (unit === "percent") return `${v.toFixed(2)}%`;
    if (unit === "rate") return v.toFixed(3);
    if (unit === "USD billions") return `US$${v.toFixed(1)}B`;
    return String(v);
  };

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
          {pair.title}
        </span>
        <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: "10px",
          color: "var(--text-muted)",
        }}>
          {formatPeriodLabel(latestPeriod)}: TW <span style={{ color: "var(--accent-teal)" }}>{formatLatest(latestTw)}</span>
          {" · "}PRC <span style={{ color: "var(--accent-red)" }}>{formatLatest(latestPrc)}</span>
        </span>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={merged} margin={{ top: 4, right: pair.dualAxis ? 36 : 12, bottom: 0, left: 0 }}>
          <XAxis
            dataKey="period"
            tickFormatter={formatPeriodLabel}
            tick={{ fontSize: 9, fontFamily: "var(--font-mono)", fill: "var(--text-muted)" }}
            axisLine={false}
            tickLine={false}
            minTickGap={28}
          />
          <YAxis
            yAxisId="tw"
            orientation="left"
            width={48}
            tick={{ fontSize: 9, fontFamily: "var(--font-mono)", fill: "var(--accent-teal)" }}
            tickFormatter={formatTick}
            axisLine={false}
            tickLine={false}
          />
          {pair.dualAxis && (
            <YAxis
              yAxisId="prc"
              orientation="right"
              width={48}
              tick={{ fontSize: 9, fontFamily: "var(--font-mono)", fill: "var(--accent-red)" }}
              tickFormatter={formatTick}
              axisLine={false}
              tickLine={false}
            />
          )}
          {unit === "percent" && <ReferenceLine y={0} yAxisId="tw" stroke="var(--border-color)" />}
          <Tooltip content={<MacroPairTooltip twLabel="Taiwan" prcLabel="PRC" unit={unit} />} />
          <Line
            type="monotone"
            yAxisId="tw"
            dataKey="tw_value"
            name="Taiwan"
            stroke="var(--accent-teal)"
            strokeWidth={2}
            dot={false}
            connectNulls
            activeDot={{ r: 4, fill: "var(--accent-teal)" }}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            yAxisId={pair.dualAxis ? "prc" : "tw"}
            dataKey="prc_value"
            name="PRC"
            stroke="var(--accent-red)"
            strokeWidth={2}
            strokeDasharray={pair.dualAxis ? undefined : "4 3"}
            dot={false}
            connectNulls
            activeDot={{ r: 4, fill: "var(--accent-red)" }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ---- PRC investment in TW by industry (MAC 7478) ----

// Bucket each industry into a coarse sector for colour coding. Anything
// not matched falls into "Other" (grey). Keep this list short and
// economically meaningful — it's an interpretive overlay, not a taxonomy.
const INDUSTRY_SECTOR = [
  { sector: "Tech / electronics", color: "#2563eb",
    match: ["電子零組件", "電腦", "資訊軟體", "電信", "研究發展", "技術檢測"] },
  { sector: "Heavy manufacturing", color: "#dc2626",
    match: ["機械設備", "電力設備", "金屬製品", "化學製品", "化學材料", "塑膠製品",
            "汽車", "醫療器材", "基本金屬", "其他製造業", "其他電子", "橡膠", "電子產品",
            "光學製品", "運輸工具", "印刷", "皮革", "木竹", "紙漿", "家具", "紡織"] },
  { sector: "Finance", color: "#7c3aed",
    match: ["銀行", "證券", "保險", "創業投資", "金融"] },
  { sector: "Services & retail", color: "#16a34a",
    match: ["批發", "零售", "餐飲", "住宿", "會議", "支援", "教育", "藝術",
            "其他服務", "專業", "不動產", "出版", "醫療"] },
  { sector: "Logistics / infra", color: "#f59e0b",
    match: ["港埠", "運輸及倉儲", "建築", "土木", "廢棄物", "農", "礦", "食品", "飲料",
            "產業用機械", "維修"] },
];

function classifySector(zh) {
  if (!zh) return { sector: "Other", color: "#6b7280" };
  for (const s of INDUSTRY_SECTOR) {
    if (s.match.some((token) => zh.includes(token))) return s;
  }
  return { sector: "Other", color: "#6b7280" };
}

// Render a USD-thousands value at the right scale: $X.XK / M / B.
// Values are stored normalised in thousands of USD across both directions.
function formatInvestmentAmount(usdK) {
  if (usdK === null || usdK === undefined) return "—";
  if (Math.abs(usdK) >= 1_000_000) return `US$${(usdK / 1_000_000).toFixed(1)}B`;
  if (Math.abs(usdK) >= 1_000)     return `US$${(usdK / 1_000).toFixed(1)}M`;
  return `US$${usdK.toFixed(0)}K`;
}

const INVESTMENT_DIRECTIONS = [
  {
    id:       "tw_to_prc",
    label:    "Taiwan → PRC",
    source:   "MAC 7473",
    since:    "1991",
    blurb:    "Approved Taiwanese investment into the mainland, cumulative since 1991.",
    analytical: (
      <>
        The dominant cross-strait capital flow. Concentrated in electronics
        manufacturing and computers/optics — the supply-chain backbone that
        followed Taiwanese firms across the strait in the 1990s–2010s. The
        single largest bucket is &ldquo;Other&rdquo;, an artefact of MAC&apos;s
        coarse outbound categorisation rather than a real industry.
      </>
    ),
  },
  {
    id:       "prc_to_tw",
    label:    "PRC → Taiwan",
    source:   "MAC 7478",
    since:    "2009-07",
    blurb:    "Approved PRC investment into Taiwan, cumulative since 2009-07.",
    analytical: (
      <>
        Vanishingly small in absolute terms — Taiwan&apos;s Investment Commission
        approves a fraction of PRC-origin applications. Most approved flow
        concentrates in wholesale/retail and electronics rather than strategic
        sectors. The asymmetry vs the Taiwan → PRC flow is roughly
        <strong> 50&times;</strong> in dollar terms.
      </>
    ),
  },
];

function InvestmentSection() {
  const [direction, setDirection] = useState("tw_to_prc");
  const [dataByDir, setDataByDir] = useState({});

  // Cache results per direction so toggling is instant after first load.
  useEffect(() => {
    if (dataByDir[direction]) return;
    fetchInvestmentByIndustry(direction, 10)
      .then((d) => setDataByDir((prev) => ({ ...prev, [direction]: d })))
      .catch(console.error);
  }, [direction, dataByDir]);

  const data = dataByDir[direction];
  const meta = INVESTMENT_DIRECTIONS.find((d) => d.id === direction);
  if (!data?.latest?.length) {
    return (
      <>
        <SectionHeader>Cross-strait investment — by industry</SectionHeader>
        <p style={{
          fontFamily: "var(--font-mono)",
          fontSize: "11px",
          color: "var(--text-muted)",
          marginBottom: "16px",
        }}>Loading…</p>
      </>
    );
  }

  const topN = 10;
  const top = data.latest.slice(0, topN);
  const rest = data.latest.slice(topN);
  const restAmount = rest.reduce((a, r) => a + (r.amount_usd_k || 0), 0);
  const restShare  = rest.reduce((a, r) => a + (r.amount_share_pct || 0), 0);
  const restCases  = rest.reduce((a, r) => a + (r.cases || 0), 0);
  const rows = [...top];
  if (rest.length) {
    rows.push({
      industry_zh: `其他 (${rest.length} 行業)`,
      industry_en: `Other (${rest.length} industries)`,
      cases: restCases,
      amount_usd_k: restAmount,
      amount_share_pct: restShare,
      _isOther: true,
    });
  }
  const maxAmount = Math.max(...rows.map((r) => r.amount_usd_k || 0));
  const totalAmount = data.latest.reduce((a, r) => a + (r.amount_usd_k || 0), 0);
  const totalCases  = data.latest.reduce((a, r) => a + (r.cases || 0), 0);

  return (
    <>
      <SectionHeader right={`${meta.source} · cumulative since ${meta.since} · through ${formatPeriodLabel(data.latest_period)}`}>
        Cross-strait investment — by industry
      </SectionHeader>

      {/* Direction toggle */}
      <div style={{ display: "flex", gap: "6px", marginBottom: "12px", flexWrap: "wrap" }}>
        {INVESTMENT_DIRECTIONS.map((d) => (
          <button
            key={d.id}
            onClick={() => setDirection(d.id)}
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
            title={d.blurb}
          >{d.label}</button>
        ))}
      </div>

      <p style={{
        fontFamily: "var(--font-body)",
        fontSize: "12px",
        color: "var(--text-secondary)",
        marginBottom: "14px",
        lineHeight: 1.5,
      }}>
        Cumulative approved investment in this direction stands at{" "}
        <strong>{formatInvestmentAmount(totalAmount)}</strong> across{" "}
        <strong>{totalCases.toLocaleString()}</strong> approved cases.{" "}
        {meta.analytical} Bar colour groups each industry into a coarse sector.
      </p>

      <div style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        padding: "14px 16px 8px",
        marginBottom: "16px",
      }}>
        <div style={{
          display: "grid",
          gridTemplateColumns: "minmax(180px, 1.2fr) 1fr 70px 80px",
          rowGap: "8px",
          columnGap: "10px",
          alignItems: "center",
          fontFamily: "var(--font-mono)",
          fontSize: "10px",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: "var(--text-muted)",
          paddingBottom: "8px",
          borderBottom: "1px solid var(--border-color)",
        }}>
          <span>Industry</span>
          <span>Share of approved amount</span>
          <span style={{ textAlign: "right" }}>Amount</span>
          <span style={{ textAlign: "right" }}>Cases</span>
        </div>
        {rows.map((r, i) => {
          const { sector, color } = r._isOther
            ? { sector: "Mixed", color: "#9ca3af" }
            : classifySector(r.industry_zh);
          const widthPct = maxAmount ? (r.amount_usd_k / maxAmount) * 100 : 0;
          return (
            <div key={i} style={{
              display: "grid",
              gridTemplateColumns: "minmax(180px, 1.2fr) 1fr 70px 80px",
              alignItems: "center",
              gap: "10px",
              padding: "8px 0",
              borderBottom: i === rows.length - 1 ? "none" : "1px solid var(--border-color)",
              fontFamily: "var(--font-body)",
              fontSize: "13px",
              color: "var(--text-primary)",
            }}>
              <div>
                <div title={sector} style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                }}>
                  <span style={{
                    display: "inline-block",
                    width: "8px", height: "8px", borderRadius: "50%",
                    background: color, flexShrink: 0,
                  }} />
                  <span>{r.industry_en || r.industry_zh}</span>
                </div>
                <div style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "10px",
                  color: "var(--text-muted)",
                  marginLeft: "16px",
                  marginTop: "1px",
                }}>{r.industry_zh}</div>
              </div>
              <div>
                <div style={{
                  position: "relative",
                  height: "10px",
                  background: "var(--bg-primary)",
                  border: "1px solid var(--border-color)",
                }}>
                  <div style={{
                    position: "absolute",
                    top: 0, left: 0, bottom: 0,
                    width: `${widthPct}%`,
                    background: color,
                    opacity: 0.85,
                  }} />
                </div>
                <div style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "10px",
                  color: "var(--text-muted)",
                  marginTop: "2px",
                }}>{r.amount_share_pct?.toFixed(1)}%</div>
              </div>
              <div style={{
                textAlign: "right",
                fontFamily: "var(--font-mono)",
                fontSize: "12px",
                color: "var(--text-primary)",
              }}>
                {formatInvestmentAmount(r.amount_usd_k)}
              </div>
              <div style={{
                textAlign: "right",
                fontFamily: "var(--font-mono)",
                fontSize: "12px",
                color: "var(--text-secondary)",
              }}>
                {(r.cases || 0).toLocaleString()}
              </div>
            </div>
          );
        })}
      </div>

      {/* Sector legend */}
      <div style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "12px",
        marginBottom: "16px",
        fontFamily: "var(--font-mono)",
        fontSize: "10px",
        color: "var(--text-muted)",
      }}>
        {INDUSTRY_SECTOR.map((s) => (
          <span key={s.sector} style={{ display: "inline-flex", alignItems: "center", gap: "5px" }}>
            <span style={{
              display: "inline-block",
              width: "8px", height: "8px", borderRadius: "50%",
              background: s.color,
            }} />
            {s.sector}
          </span>
        ))}
      </div>

      {/* MAC vs MOFCOM verification — only when looking at outbound (TW → PRC).
          MOFCOM doesn't publish a country-destination breakdown for outbound
          PRC FDI to Taiwan, so there's no counterpart for the inbound view. */}
      {direction === "tw_to_prc" && <InvestmentVerification />}
    </>
  );
}

function InvestmentVerification() {
  const [data, setData] = useState(null);
  useEffect(() => {
    fetchInvestmentVerification().then(setData).catch(console.error);
  }, []);

  if (!data?.pairs?.length) return null;

  const cum     = data.cumulative;
  const macCum  = cum?.mac_amount_usd_b;
  const mofCum  = cum?.mofcom_amount_usd_b;
  const cumRatio = cum?.utilisation_ratio_pct;
  const cumYear = cum?.year;

  // Bar chart: pair MAC vs MOFCOM per year
  const maxAnnual = Math.max(
    ...data.pairs.flatMap((p) => [p.mac_approved_usd_b || 0, p.mofcom_actual_usd_b || 0])
  );

  return (
    <div style={{ marginTop: "30px", marginBottom: "20px" }}>
      <div style={{
        height: "2px",
        background: "var(--border-color)",
        marginBottom: "9px",
      }} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: "11px",
          fontWeight: 600,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: "var(--text-primary)",
        }}>
          Verification — MAC approved vs MOFCOM actually used
        </span>
        <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: "10px",
          color: "var(--text-muted)",
        }}>
          <a href={data.mofcom_source_url} target="_blank" rel="noreferrer" style={{
            color: "var(--text-muted)", textDecoration: "underline dotted",
          }}>{data.mofcom_source_label}</a>
          {" · extracted "}{data.mofcom_extracted_at}
        </span>
      </div>
      <div style={{ height: "1px", background: "var(--border-color)", marginTop: "9px", marginBottom: "14px" }} />

      {/* Cumulative headline */}
      {macCum && mofCum && (
        <div style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          padding: "14px 18px",
          marginBottom: "14px",
        }}>
          <div style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr 1fr",
            gap: "16px",
          }}>
            <div>
              <div style={{
                fontFamily: "var(--font-mono)",
                fontSize: "10px",
                color: "var(--text-muted)",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                marginBottom: "4px",
              }}>MAC approved · cumulative end-{cumYear}</div>
              <div style={{
                fontFamily: "var(--font-serif, Georgia, serif)",
                fontSize: "20px",
                color: "var(--text-primary)",
              }}>
                <strong>US${macCum.toFixed(1)}B</strong>
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)", marginTop: "2px" }}>
                Since {cum.mac_start_year}
              </div>
            </div>
            <div>
              <div style={{
                fontFamily: "var(--font-mono)",
                fontSize: "10px",
                color: "var(--text-muted)",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                marginBottom: "4px",
              }}>MOFCOM actually used · cumulative end-{cumYear}</div>
              <div style={{
                fontFamily: "var(--font-serif, Georgia, serif)",
                fontSize: "20px",
                color: "var(--text-primary)",
              }}>
                <strong>US${mofCum.toFixed(1)}B</strong>
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)", marginTop: "2px" }}>
                Since ~{cum.mofcom_start_year_approx} ({cum.mofcom_companies?.toLocaleString()} companies)
              </div>
            </div>
            <div>
              <div style={{
                fontFamily: "var(--font-mono)",
                fontSize: "10px",
                color: "var(--text-muted)",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                marginBottom: "4px",
              }}>Utilisation ratio</div>
              <div style={{
                fontFamily: "var(--font-serif, Georgia, serif)",
                fontSize: "20px",
                color: "#dc2626",
              }}>
                <strong>{cumRatio.toFixed(0)}%</strong>
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)", marginTop: "2px" }}>
                MOFCOM ÷ MAC
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Annual paired bars */}
      <div style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        padding: "14px 16px 8px",
      }}>
        <div style={{
          fontFamily: "var(--font-mono)",
          fontSize: "10px",
          color: "var(--text-muted)",
          marginBottom: "8px",
        }}>
          MAC annuals derived as end-of-year cumulative differences from
          MAC 7473. Years where either side is missing are omitted.
        </div>
        <div style={{
          display: "flex",
          gap: "14px",
          fontFamily: "var(--font-mono)",
          fontSize: "10px",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: "var(--text-muted)",
          paddingBottom: "10px",
          borderBottom: "1px solid var(--border-color)",
          alignItems: "center",
        }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "5px" }}>
            <span style={{ width: "10px", height: "10px", background: "#0d9488" }} />
            MAC approved
          </span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "5px" }}>
            <span style={{ width: "10px", height: "10px", background: "#dc2626" }} />
            MOFCOM actually used
          </span>
          <span style={{ marginLeft: "auto" }}>USD billions, annual</span>
        </div>
        {data.pairs.map((p) => {
          const macW = maxAnnual ? ((p.mac_approved_usd_b || 0) / maxAnnual * 100) : 0;
          const mofW = maxAnnual ? ((p.mofcom_actual_usd_b || 0) / maxAnnual * 100) : 0;
          return (
            <div key={p.year} style={{
              padding: "10px 0",
              borderBottom: "1px solid var(--border-color)",
              display: "grid",
              gridTemplateColumns: "44px 1fr 100px",
              gap: "10px",
              alignItems: "center",
            }}>
              <div style={{
                fontFamily: "var(--font-mono)",
                fontSize: "12px",
                color: "var(--text-primary)",
              }}>{p.year}</div>
              <div>
                {/* MAC bar */}
                <div style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  marginBottom: "4px",
                }}>
                  <div style={{
                    flex: 1,
                    height: "12px",
                    background: "var(--bg-primary)",
                    border: "1px solid var(--border-color)",
                    position: "relative",
                  }}>
                    <div style={{
                      position: "absolute",
                      top: 0, left: 0, bottom: 0,
                      width: `${macW}%`,
                      background: "#0d9488",
                      opacity: 0.85,
                    }} />
                  </div>
                  <span style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "11px",
                    color: "var(--text-secondary)",
                    minWidth: "55px",
                    textAlign: "right",
                  }}>
                    {p.mac_approved_usd_b != null ? `$${p.mac_approved_usd_b.toFixed(2)}B` : "—"}
                  </span>
                </div>
                {/* MOFCOM bar */}
                <div style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                }}>
                  <div style={{
                    flex: 1,
                    height: "12px",
                    background: "var(--bg-primary)",
                    border: "1px solid var(--border-color)",
                    position: "relative",
                  }}>
                    <div style={{
                      position: "absolute",
                      top: 0, left: 0, bottom: 0,
                      width: `${mofW}%`,
                      background: "#dc2626",
                      opacity: 0.85,
                    }} />
                  </div>
                  <span style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "11px",
                    color: "var(--text-secondary)",
                    minWidth: "55px",
                    textAlign: "right",
                  }}>
                    {p.mofcom_actual_usd_b != null ? `$${p.mofcom_actual_usd_b.toFixed(2)}B` : "—"}
                  </span>
                </div>
              </div>
              <div style={{
                textAlign: "right",
                fontFamily: "var(--font-mono)",
                fontSize: "11px",
                color: p.utilisation_ratio_pct != null && p.utilisation_ratio_pct < 25 ? "#dc2626" : "var(--text-secondary)",
              }}>
                {p.utilisation_ratio_pct != null
                  ? `${p.utilisation_ratio_pct.toFixed(0)}% used`
                  : "—"}
              </div>
            </div>
          );
        })}
      </div>

      <p style={{
        fontFamily: "var(--font-body)",
        fontSize: "12px",
        color: "var(--text-secondary)",
        marginTop: "14px",
        lineHeight: 1.5,
      }}>
        The gap is structural. <strong>MAC counts at approval</strong>{" "}
        (with annual flows from Taiwan's Investment Commission, cumulative
        since 1991). <strong>MOFCOM counts at actual capital landing</strong>{" "}
        attributed by <em>immediate</em> source country (cumulative since
        records began ~1988 — coinciding with the 1988 国务院 document
        encouraging Taiwanese investment). The two start dates differ by
        ~3 years; 1988-1990 flows were small relative to the full window,
        so this affects the comparison only marginally. The two-thirds
        gap is driven by (1) approved-but-not-deployed investment, and
        (2) Taiwanese capital routed via Cayman, BVI or HK subsidiaries
        — which MOFCOM books under those source jurisdictions rather than
        Taiwan. The utilisation ratio has fallen from ~50% in 2017 to
        ~15% recently, suggesting the offshore-routing share is growing.
      </p>
      <p style={{
        fontFamily: "var(--font-body)",
        fontSize: "12px",
        color: "var(--text-secondary)",
        marginTop: "10px",
        marginBottom: "0",
        lineHeight: 1.5,
        padding: "10px 14px",
        background: "rgba(220,38,38,0.06)",
        border: "1px solid rgba(220,38,38,0.18)",
      }}>
        <strong style={{ color: "#991b1b" }}>Scale caveat:</strong> Both
        figures likely undercount the true cross-strait flow. Academic
        consensus (PIIE, China Quarterly) is that the majority of
        Taiwanese FDI booked under <em>Hong Kong, Singapore and Caribbean
        tax havens</em> in fact deploys in China — so MAC's $210B omits
        a large share of capital that left Taiwan but was approved for
        offshore destinations. For pace comparison: TSMC alone has
        committed roughly <strong>US$165B to its Arizona expansion in
        the past ~5 years</strong> — close to <em>80% of all the
        Taiwan→PRC investment MAC has approved over the 35 years since
        1991</em>, but compressed into a fraction of the time. Taiwanese
        capex is migrating away from PRC and toward the US, Japan and
        Southeast Asia post-2018. The story this chart tells is therefore
        narrower than it appears — it's the gap between
        Taiwanese-government-approved and PRC-government-claimed figures
        for the subset of capital that <em>both sides acknowledge</em>;
        the shadow flow is larger still.
      </p>
    </div>
  );
}

// ---- People section: bidirectional cross-strait residency ----
//
// Tells two asymmetric stories side by side:
//   * LEFT: PRC citizens resident in Taiwan — annual NIA-issued residence
//     and settlement permits since 2016 (8 years × 2 metrics). Bars rather
//     than lines because it's a discrete flow.
//   * RIGHT: Taiwanese resident in PRC — curated milestones from PRC public
//     bureaus (台胞证 cumulative 1992-2019, 2020 census, 2024 partial NIA
//     issuance) plus a vertical policy timeline.
// The bottom strip pairs MAC's monthly visitor flow series (TW→PRC vs
// PRC→TW) so the stock figures above sit alongside the flow context.

const POLICY_DOT_COLOR = "var(--accent-amber)";

function formatLargeNumber(n) {
  if (n === null || n === undefined) return "—";
  if (n >= 1e6) return `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(n >= 1e5 ? 0 : 1)}K`;
  return n.toLocaleString();
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
  // Combine into [{period, residence, settlement}] for grouped bars.
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

function PeopleFlowChart({ tw, prc }) {
  // Merge the two monthly series for a paired line chart, intersection only.
  const byPeriod = {};
  for (const r of tw?.series || []) byPeriod[r.period] = { period: r.period, tw: r.value };
  for (const r of prc?.series || []) byPeriod[r.period] = { ...byPeriod[r.period], period: r.period, prc: r.value };
  // Limit to last 60 months for readability.
  const all = Object.values(byPeriod).sort((a, b) => a.period.localeCompare(b.period));
  const data = all.slice(-60);

  return (
    <div style={{ height: "200px", marginTop: "8px" }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="var(--border-color)" />
          <XAxis
            dataKey="period"
            tick={{ fontFamily: "var(--font-mono)", fontSize: 10, fill: "var(--text-muted)" }}
            stroke="var(--border-color)"
            tickFormatter={(p) => p?.slice(0, 4)}
            interval="preserveStartEnd"
            minTickGap={40}
          />
          <YAxis
            tick={{ fontFamily: "var(--font-mono)", fontSize: 10, fill: "var(--text-muted)" }}
            stroke="var(--border-color)"
            tickFormatter={(v) => `${v}`}
          />
          <Tooltip
            contentStyle={{
              background: "var(--bg-primary)",
              border: "1px solid var(--border-color)",
              fontFamily: "var(--font-mono)",
              fontSize: "11px",
            }}
            formatter={(v, key) => [
              v ? `${(v * 10000).toLocaleString()} persons` : "—",
              key === "tw" ? "TW → PRC" : "PRC → TW",
            ]}
          />
          <Line type="monotone" dataKey="tw" stroke="var(--text-primary)" strokeWidth={1.5} dot={false} />
          <Line type="monotone" dataKey="prc" stroke="var(--accent-teal, #14B8A6)" strokeWidth={1.5} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function PeopleSection() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetchPeopleRecords()
      .then(setData)
      .catch(() => setError(true));
  }, []);

  if (error) {
    return (
      <>
        <SectionHeader>Cross-strait residency &amp; people flow</SectionHeader>
        <p style={{ color: "var(--accent-red)", fontFamily: "var(--font-mono)", fontSize: "12px" }}>
          Couldn't load people-records.
        </p>
      </>
    );
  }
  if (!data) {
    return (
      <>
        <SectionHeader>Cross-strait residency &amp; people flow</SectionHeader>
        <p style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: "11px" }}>Loading…</p>
      </>
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
    <>
      <SectionHeader right={data.meta?.extracted_at ? `latest curated ${data.meta.extracted_at}` : null}>
        Cross-strait residency &amp; people flow
      </SectionHeader>

      <p style={{
        fontFamily: "var(--font-body)",
        fontSize: "13px",
        color: "var(--text-secondary)",
        marginBottom: "16px",
        lineHeight: 1.5,
      }}>
        How many people live on the other side of the strait. PRC residents in Taiwan are
        tracked by Taiwan's NIA via residence and settlement permits; Taiwanese in PRC are
        only knowable through PRC bureaus — 台胞证 issuance counts, the 2020 census, and
        occasional NIA press releases. Stock above, flow (monthly visitors) below.
      </p>

      {/* Headline KPI strip */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
        gap: "10px",
        marginBottom: "20px",
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
            footnote="No 籍貫 census on TW side since 1992"
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

          {/* Milestones */}
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

          {/* Policy timeline */}
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

      {/* Bottom: flow strip — paired monthly visitors */}
      <div style={{
        padding: "14px 16px",
        border: "1px solid var(--border-color)",
        background: "var(--bg-card)",
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
          }}>Monthly visitor flows — last 60 months</h3>
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
          (teal). The asymmetry — roughly 7× more outbound than inbound, post-reopening —
          is the live flow story behind the residency stock above.
        </p>
        <PeopleFlowChart tw={data.flows?.tw_visitors_to_prc} prc={data.flows?.prc_visitors_to_tw} />
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
        2020 PRC Census Bulletin No.8. Refresh: {sources || "annual"}. The 1992 cutover from
        ROC household registration's 籍貫 field means modern PRC-origin counts on the TW side
        come from NIA permits, not census ancestry data.
      </p>
    </>
  );
}

function MacroSection({ seriesById, monthsLimit }) {
  // Bail if 7888 hasn't been scraped yet (any one pair missing data is enough)
  const allLoaded = MACRO_PAIRS.every(
    (p) => seriesById[p.tw]?.points?.length && seriesById[p.prc]?.points?.length
  );
  if (!allLoaded) return null;
  return (
    <>
      <SectionHeader>Macro — TW vs PRC</SectionHeader>
      <p style={{
        fontFamily: "var(--font-body)",
        fontSize: "12px",
        color: "var(--text-secondary)",
        marginBottom: "14px",
        lineHeight: 1.5,
      }}>
        The two economies side-by-side. Real GDP growth and consumer-price inflation
        share a single axis; FX reserves and exchange rates use dual axes because TW
        and PRC operate at very different scales. GDP appears quarterly (one dot per
        quarter); other series are monthly.
      </p>
      {MACRO_PAIRS.map((pair) => (
        <MacroPairChart
          key={pair.id}
          pair={pair}
          seriesById={seriesById}
          monthsLimit={monthsLimit}
        />
      ))}
    </>
  );
}

// ---- Verification section ----

// Per-kind presentation: section header, intro paragraph, and the colour for
// the "second reporter" line (TW MAC always uses accent-teal as reporter A).
const VERIFICATION_KINDS = {
  prc_customs: {
    section_label: "Verification — MAC vs PRC Customs",
    reporter_b_color: "var(--accent-red)",
    chart_months: 60,
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
    section_label: "Verification — MAC vs HK Customs (MAC compilation)",
    reporter_b_color: "var(--accent-purple)",
    chart_months: 60,
    intro: (
      <>
        TW-HK trade as compiled by MAC dataset 7459, which republishes HK Customs
        figures alongside TW Customs. Solid line: Taiwan's MAC. Dashed line: HK Customs
        (via MAC). The TW→HK leg usually agrees within a few percent, but HK records
        far more outbound trade to Taiwan than TW records as imports from HK — most of
        HK's exports to TW are PRC-origin goods that TW books as imports from the
        mainland instead.
      </>
    ),
    empty_message: "TW-HK trade data not yet loaded. Run scrape_mac_hk_trade.",
  },
  hk_csd_direct: {
    section_label: "Verification — MAC vs HK CSD (direct, third reporter)",
    reporter_b_color: "var(--accent-teal)",
    chart_months: 60,
    intro: (
      <>
        Same TW-HK flows, but sourced <em>directly</em> from Hong Kong's Census &amp;
        Statistics Department (Tables 410-50012 / 410-50013, HKD converted to USD at
        the 7.78 peg) rather than via MAC&apos;s compilation. Lets us cross-check both
        MAC&apos;s compilation accuracy <em>and</em> see the HK transit gap from a
        third independent angle. HK CSD has data back to 1972, but the chart shows
        the last 60 months for readability — early-decade magnitudes are orders of
        magnitude smaller and would compress the modern story.
      </>
    ),
    empty_message: "HK CSD data not yet loaded. Run scrape_hk_census.",
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

function VerificationKindSubsection({ kind, pairs }) {
  const cfg = VERIFICATION_KINDS[kind];
  if (!cfg) return null;
  // Trim to chart_months per kind. null/undefined = keep the full series.
  const limit = cfg.chart_months;
  const trimmedPairs = limit
    ? pairs.map((p) => ({ ...p, points: (p.points || []).slice(-limit) }))
    : pairs;
  const hasData = trimmedPairs.some((p) => p.points.some((pt) => pt.value_b !== null));
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
        trimmedPairs.map((pair) => (
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
    // Fetch the full history; trim per-kind in VerificationKindSubsection.
    // The HK CSD direct pair goes back to 1972 — only ~1300 numeric points
    // across all pairs, well within Recharts comfort.
    fetchEconomyVerification({})
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
