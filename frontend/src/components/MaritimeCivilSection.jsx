import { useEffect, useMemo, useState } from "react";
import { StatGrid, StatBlock } from "./documentChrome";
import {
  fetchMaritimeSummary, fetchMaritimeCivilMonthly, fetchMaritimeCivilVessels, fetchMaritimeSarMonthly,
  fetchCoastGuardEnforcement,
} from "../api";
import CoastGuardMap from "./CoastGuardMap";
import {
  FORCE_COLOUR, Pill, GROUPS, RANGES, fmtInt, addMonths, SrcLink, SubHeader, deltaText, Caveats, MonthlyStrip, latestSource,
} from "./coastGuardShared";
import { Copy } from "../copy";

// Civilian fleets & radar-only detections — the Maritime tab's militia /
// dredger layer (Phase 2g), named after what is measured. Sits under the
// Coast Guard section and shares its primitives so the page reads as one
// instrument. Three rules carried over: every chart renders its scoped caveat
// from `summary.caveats`; PRC and Taiwan series never share a mark (the
// red/green side palette fails the CVD check when adjacent); and the mirror
// stays in view — PRC fishing presence (AIS) is paired with the CGA's own
// count of PRC fishing vessels expelled (the same hulls, counted from the
// other side). Radar rows are NEUTRAL grey: an unmatched detection has no
// side — that is the point of it.
const PRC = FORCE_COLOUR.CCG;          // PRC side red
const TW = FORCE_COLOUR.CGA;           // Taiwan side green
const RADAR = "var(--text-secondary)"; // no side
const RADAR_HUE = "108, 108, 108";     // rgb triple for the map fill (light tiles in both themes)
const FRAME = { fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.5 };
const MONO = { fontFamily: "var(--font-mono)", fontSize: "10.5px", color: "var(--text-secondary)" };
const CLASS_PILLS = [
  { id: "", label: "All named hulls" },
  { id: "OTHER", label: "Non-fishing" },
  { id: "FISHING", label: "Fishing" },
  { id: "militia", label: "Roster-listed" },
];
const pct = (x) => (x === null || x === undefined ? "—" : `${(x * 100).toFixed(0)}%`);
const zoneShort = (id) => id.replace(/_/g, " ").replace("prohibited", "prohib.").replace("restricted", "restr.").replace("contiguous", "24 nm");

function ZoneTable({ zones }) {
  const cols = [
    { key: "chn_fishing", label: "PRC fishing", get: (z) => z.chn_fishing },
    { key: "chn_other", label: "PRC non-fishing", get: (z) => z.chn_other },
    { key: "unmatched", label: "Radar · no AIS", get: (z) => z.sar?.unmatched || 0 },
  ];
  const max = {};
  for (const c of cols) max[c.key] = Math.max(1, ...zones.map((z) => c.get(z) || 0));
  return (
    <div style={{ overflowX: "auto", border: "1px solid var(--border-color)", background: "var(--bg-card)" }}>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr style={{ fontFamily: "var(--font-mono)", fontSize: "9.5px", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--text-muted)" }}>
            <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 600 }}>Zone</th>
            {cols.map((c) => <th key={c.key} style={{ textAlign: "right", padding: "6px 8px", fontWeight: 600 }}>{c.label}</th>)}
            <th style={{ textAlign: "right", padding: "6px 8px", fontWeight: 600 }}>dark share</th>
          </tr>
        </thead>
        <tbody>
          {zones.map((z) => {
            const tot = (z.sar?.matched || 0) + (z.sar?.unmatched || 0);
            return (
              <tr key={z.zone_id} style={{ borderTop: "1px solid var(--border-color)" }}>
                <td style={{ padding: "5px 8px", fontFamily: "var(--font-body)", fontSize: "11.5px", color: "var(--text-primary)", whiteSpace: "nowrap" }}>
                  {z.label_en}
                  {z.group === "taiwan_bank" && <span title="Analytical box — see Taiwan Bank caveat" style={{ color: "var(--flag)", marginLeft: 5, fontSize: "9.5px" }}>⚑</span>}
                  <span style={{ display: "block", fontFamily: "var(--font-mono)", fontSize: "9.5px", color: "var(--text-muted)" }}>{z.label_zh}</span>
                </td>
                {cols.map((c) => {
                  const v = c.get(z) || 0;
                  const t = v / max[c.key];
                  return (
                    <td key={c.key} style={{ padding: "5px 8px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-primary)",
                                             background: v ? `rgba(124,124,124,${0.06 + t * 0.32})` : "transparent", whiteSpace: "nowrap" }}>
                      {v ? fmtInt(v) : <span style={{ color: "var(--text-muted)" }}>·</span>}
                    </td>
                  );
                })}
                <td style={{ padding: "5px 8px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: "11px", color: tot ? "var(--text-primary)" : "var(--text-muted)" }}>
                  {tot ? pct((z.sar.unmatched || 0) / tot) : "·"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div style={{ padding: "5px 8px", fontFamily: "var(--font-mono)", fontSize: "9.5px", color: "var(--text-muted)" }}>
        hull-days (AIS) · radar detections per pass · dark share = detections with no AIS match ÷ all detections
      </div>
    </div>
  );
}

function VesselTable({ vessels, classLabels }) {
  if (!vessels.length) {
    return <div style={{ ...MONO, color: "var(--text-muted)", padding: "8px 0" }}>No named hulls in window.</div>;
  }
  return (
    <div style={{ overflowX: "auto", border: "1px solid var(--border-color)", background: "var(--bg-card)" }}>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr style={{ fontFamily: "var(--font-mono)", fontSize: "9.5px", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--text-muted)" }}>
            {["Hull", "MMSI", "Flag", "Class", "Zones", "Days", "Hours"].map((h, i) => (
              <th key={h} style={{ textAlign: i >= 5 ? "right" : "left", padding: "6px 8px", fontWeight: 600 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {vessels.map((v) => (
            <tr key={v.mmsi} style={{ borderTop: "1px solid var(--border-color)" }}>
              <td style={{ padding: "5px 8px", fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-primary)", whiteSpace: "nowrap" }}>
                {v.name || <span style={{ color: "var(--text-muted)" }}>(no name broadcast)</span>}
                {v.militia_source && (
                  <span style={{ marginLeft: 6, fontSize: "9px", letterSpacing: "0.06em", textTransform: "uppercase", padding: "1px 5px",
                                 border: `1px solid ${PRC}`, color: PRC }} title={`Linked to the maritime militia by ${v.militia_source} (the study's inference, not proof)${v.militia_name_zh ? ` — ${v.militia_name_zh}${v.militia_port ? `, ${v.militia_port}` : ""}` : ""}`}>
                    <SrcLink href={v.militia_url}>roster</SrcLink>
                  </span>
                )}
              </td>
              <td style={{ padding: "5px 8px", fontFamily: "var(--font-mono)", fontSize: "10.5px", color: "var(--text-secondary)" }}>{v.mmsi}</td>
              <td style={{ padding: "5px 8px", fontFamily: "var(--font-mono)", fontSize: "10.5px", color: v.flag === "CHN" ? PRC : v.flag === "TWN" ? TW : "var(--text-secondary)" }}>{v.flag || "—"}</td>
              <td style={{ padding: "5px 8px", fontFamily: "var(--font-body)", fontSize: "11px", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>{classLabels?.[v.vessel_class] || v.vessel_class}</td>
              <td style={{ padding: "5px 8px", fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)" }}>{v.zones.map(zoneShort).join(" · ")}</td>
              <td style={{ padding: "5px 8px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-primary)" }}>{fmtInt(v.hull_days)}</td>
              <td style={{ padding: "5px 8px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-secondary)" }}>{fmtInt(Math.round(v.hours))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function MaritimeCivilSection() {
  const [summary, setSummary] = useState(null);
  const [monthly, setMonthly] = useState(null);
  const [sarMonthly, setSarMonthly] = useState(null);
  const [enforcement, setEnforcement] = useState(null);
  const [vessels, setVessels] = useState(null);
  const [group, setGroup] = useState("kinmen");
  const [range, setRange] = useState(36);
  const [cls, setCls] = useState("");
  const [error, setError] = useState(false);

  useEffect(() => {
    Promise.all([
      fetchMaritimeSummary(30).then(setSummary),
      fetchCoastGuardEnforcement({ months: 240 }).then(setEnforcement),
    ]).catch(() => setError(true));
  }, []);

  useEffect(() => {
    const params = { months: range };
    if (group) params.group = group;
    fetchMaritimeCivilMonthly({ ...params, flag: "CHN" }).then((d) => setMonthly(d.rows || [])).catch(() => setMonthly([]));
    fetchMaritimeSarMonthly(params).then((d) => setSarMonthly(d.rows || [])).catch(() => setSarMonthly([]));
  }, [group, range]);

  useEffect(() => {
    const params = { days: 30, limit: 15 };
    if (cls === "militia") params.militia = 1; else if (cls) params.vessel_class = cls;
    fetchMaritimeCivilVessels(params).then((d) => setVessels(d.vessels || [])).catch(() => setVessels([]));
  }, [cls]);

  // One month axis for the four strips (zero-filled where the series exists,
  // null where it doesn't — a SAR month with no pass is not a zero).
  const paired = useMemo(() => {
    if (!monthly || !sarMonthly || !summary?.latest_date) return [];
    const latest = summary.latest_date.slice(0, 7);
    const start = addMonths(latest, -(range - 1));
    const floor = (summary.coverage_start || "2017-01").slice(0, 7);
    const from = start < floor ? floor : start;
    const byMonth = {};
    for (let m = from; m <= latest; m = addMonths(m, 1)) byMonth[m] = { month: m, FISHING: 0, OTHER: 0, expelled: null, unmatched: null, dark_share: null };
    for (const r of monthly) if (byMonth[r.month] && r.vessel_class in byMonth[r.month]) byMonth[r.month][r.vessel_class] = r.hull_days;
    for (const r of enforcement?.monthly || []) if (byMonth[r.period]) byMonth[r.period].expelled = r.expelled;
    for (const r of sarMonthly) if (byMonth[r.month]) { byMonth[r.month].unmatched = r.unmatched; byMonth[r.month].dark_share = r.dark_share === null ? null : Math.round(r.dark_share * 100); }
    return Object.values(byMonth);
  }, [monthly, sarMonthly, enforcement, summary, range]);

  if (error) {
    return <p style={{ color: "var(--accent-red)", fontFamily: "var(--font-mono)", fontSize: "13px", padding: "20px 0" }}>Couldn't load civilian-fleet data.</p>;
  }
  if (!summary) {
    return <p style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: "13px", padding: "20px 0" }}>Loading civilian fleets…</p>;
  }
  if (!summary.latest_date) {
    return <p style={{ ...MONO, color: "var(--text-muted)", padding: "12px 0" }}>Civilian-fleet layer: no data yet (the backfill has not run against this database).</p>;
  }

  const civil = (flag, c) => summary.civil.find((x) => x.flag === flag && x.vessel_class === c) || {};
  const prcFish = civil("CHN", "FISHING"), prcOther = civil("CHN", "OTHER"), twFish = civil("TWN", "FISHING");
  const sar = summary.sar;
  const groupMeta = GROUPS.find((g) => g.id === group);
  const t81 = latestSource(enforcement?.sources, "表8-1");
  const t81Link = t81 ? <SrcLink href={t81.source_url} muted>({t81.source_ref})</SrcLink> : null;
  const hasSar = paired.some((r) => r.unmatched !== null);
  const caveatScopes = [hasSar ? "sar" : null, group === "taiwan_bank" ? "taiwan_bank" : null].filter(Boolean);
  const roster = summary.militia || { roster_size: 0, seen: [] };
  const mapValue = (z) => (z?.chn_fishing || 0) + (z?.chn_other || 0);
  const mapLines = (z) => {
    const s = z?.sar;
    const tot = s ? (s.matched || 0) + (s.unmatched || 0) : 0;
    return `<div>PRC fishing: <b>${z?.chn_fishing || 0}</b> hull-days</div>` +
           `<div>PRC non-fishing: <b>${z?.chn_other || 0}</b> hull-days</div>` +
           `<div>Radar, no AIS match: <b>${s ? s.unmatched : 0}</b> detections${tot ? ` · ${Math.round((s.unmatched / tot) * 100)}% of ${tot}` : ""}</div>`;
  };

  return (
    <>
      <SubHeader right={`AIS to ${summary.latest_date}${summary.sar_latest_date ? ` · radar to ${summary.sar_latest_date}` : ""}`}>Civilian fleets & radar-only detections</SubHeader>
      <Copy k="maritime.civil.intro" style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--text-secondary)", lineHeight: 1.55, margin: "0 0 14px" }}
            fallback={"PRC- and Taiwan-flagged civilian hulls in the same zones, beside Sentinel-1 radar detections with and without an AIS match."} />
      <Caveats caveats={summary.caveats} scopes={["all"]} />

      {/* KPI band — PRC pair, Taiwan mirror, radar remainder (neutral) */}
      <StatGrid columns={4}>
        <StatBlock label="PRC fishing · 30 days" accent={PRC} value={fmtInt(prcFish.hull_days)}
                   note={`hull-days, all zones · ${deltaText(prcFish.hull_days, prcFish.prev_hull_days) || ""}`} />
        <StatBlock label="PRC non-fishing · 30 days" accent={PRC} value={fmtInt(prcOther.hull_days)}
                   note={`hull-days · GFW class “other” (tugs, dredgers, supply, survey) · ${deltaText(prcOther.hull_days, prcOther.prev_hull_days) || ""}`} />
        <StatBlock label="Taiwan fishing · 30 days" accent={TW} value={fmtInt(twFish.hull_days)}
                   note={`hull-days, all zones · ${deltaText(twFish.hull_days, twFish.prev_hull_days) || ""}`} />
        <StatBlock label={`Radar, no AIS match · ${summary.days} days`} accent={RADAR} value={sar ? fmtInt(sar.current.unmatched) : "—"}
                   note={sar ? `detections · ${pct(sar.current.dark_share)} of ${fmtInt(sar.current.matched + sar.current.unmatched)} radar detections · ${deltaText(sar.current.unmatched, sar.previous.unmatched) || ""}` : "no radar data yet"} />
      </StatGrid>

      {/* Paired monthly strips */}
      <SubHeader right={`AIS-visible to ${summary.latest_date}`}>Fleets vs enforcement vs radar · monthly</SubHeader>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 10 }}>
        {GROUPS.map((g) => <Pill key={g.id} active={group === g.id} onClick={() => setGroup(g.id)}>{g.label}</Pill>)}
        <span style={{ width: 10 }} />
        {RANGES.map((r) => <Pill key={r.months} active={range === r.months} onClick={() => setRange(r.months)}>{r.label}</Pill>)}
      </div>
      {paired.length ? (
        <>
          <MonthlyStrip data={paired} dataKey="FISHING" colour={PRC} syncId="mar-paired" unit="hull-days"
                        title={`PRC-flagged fishing hull-days · ${groupMeta.label}`} />
          <MonthlyStrip data={paired} dataKey="OTHER" colour={PRC} syncId="mar-paired" unit="hull-days" height={100}
                        title={`PRC-flagged non-fishing hull-days (GFW “other”) · ${groupMeta.label}`} />
          <MonthlyStrip data={paired} dataKey="expelled" colour={TW} syncId="mar-paired" unit="expelled" height={100}
                        title="PRC fishing vessels expelled by the CGA · national, all waters" titleLink={t81Link} />
          {hasSar && (
            <>
              <MonthlyStrip data={paired} dataKey="unmatched" colour={RADAR} syncId="mar-paired" unit="detections" height={100}
                            title={`Radar detections with no AIS match · ${groupMeta.label}`} />
              <MonthlyStrip data={paired} dataKey="dark_share" colour={RADAR} syncId="mar-paired" unit="% of radar detections" height={80}
                            title={`Share of radar detections with no AIS match · ${groupMeta.label}`} />
            </>
          )}
        </>
      ) : (
        <div style={{ ...MONO, color: "var(--text-muted)", padding: "12px 0" }}>Loading…</div>
      )}
      <Caveats caveats={summary.caveats} scopes={caveatScopes} compact />

      {/* Dual-frame reading — both, always */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12, marginTop: 12 }}>
        <div style={{ padding: "10px 12px", border: "1px solid var(--border-color)", borderLeft: `3px solid ${TW}`, background: "var(--bg-card)" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "9.5px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 4 }}>Read from Taipei</div>
          <Copy k="maritime.civil.frame_taipei" as="div" style={FRAME} fallback={"PRC fishing and dredging hulls inside Taiwan's lines are trespass to be expelled; formations during PLA activity are read as militia."} />
        </div>
        <div style={{ padding: "10px 12px", border: "1px solid var(--border-color)", borderLeft: `3px solid ${PRC}`, background: "var(--bg-card)" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "9.5px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 4 }}>Read from Beijing</div>
          <Copy k="maritime.civil.frame_beijing" as="div" style={FRAME} fallback={"Beijing recognises none of the lines and describes the same hulls as fishing vessels on traditional grounds."} />
        </div>
      </div>

      {/* Map + zone table */}
      <SubHeader right={`${summary.window_start} → ${summary.latest_date}`}>Zones · 30-day window</SubHeader>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 16, alignItems: "start" }}>
        <CoastGuardMap zoneStats={summary.zones} value={mapValue} lines={mapLines} hue={RADAR_HUE}
                       legend={["Fill: PRC-flagged civilian hull-days in window · hover for radar", "Solid = prohibited · dashed = restricted · dotted = bands · fine-dotted = Taiwan Bank"]} />
        <ZoneTable zones={summary.zones} />
      </div>
      <Caveats caveats={summary.caveats} scopes={["taiwan_bank"]} compact />

      {/* Named hulls */}
      <SubHeader right={`Last 30 days · top 15 by hull-days`}>Named hulls</SubHeader>
      <Copy k="maritime.civil.vessels" style={{ fontFamily: "var(--font-body)", fontSize: "11.5px", color: "var(--text-secondary)", margin: "0 0 8px", lineHeight: 1.5 }}
            fallback={"Per-hull rows exist for PRC hulls in the small zones, PRC non-fishing hulls everywhere, and roster-listed hulls anywhere."} />
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
        {CLASS_PILLS.map((p) => <Pill key={p.id} active={cls === p.id} onClick={() => setCls(p.id)}>{p.label}</Pill>)}
        <span style={{ ...MONO, marginLeft: "auto" }}>
          roster: {fmtInt(roster.roster_size)} hulls the study linked to the militia · {fmtInt(roster.seen.length)} seen in any zone since {roster.since || "—"}
        </span>
      </div>
      {vessels ? <VesselTable vessels={vessels} classLabels={summary.class_labels} /> : <div style={{ ...MONO, color: "var(--text-muted)", padding: "8px 0" }}>Loading…</div>}
      <Caveats caveats={summary.caveats} scopes={["militia"]} compact />

      <p style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)", marginTop: "16px", lineHeight: 1.5 }}>
        <strong style={{ color: "var(--text-secondary)" }}>Sources:</strong> <SrcLink href="https://globalfishingwatch.org/our-apis/" muted>Global Fishing Watch</SrcLink> 4Wings presence
        (AIS, per hull per day per 1-km cell, coverage from {summary.coverage_start}; vessel class is GFW's inference) and
        <SrcLink href="https://globalfishingwatch.org/platform-update/2024-may-global-fishing-watch-apis-new-dataset-in-4wings-api-featuring-vessel-detections-from-sentinel-1-sar/" muted> SAR vessel detections</SrcLink> (Sentinel-1, matched to AIS by GFW{sar?.coverage_start ? `, from ${sar.coverage_start}` : ""}) ·
        militia roster: <SrcLink href="https://csis-website-prod.s3.amazonaws.com/s3fs-public/publication/211118_Poling_Maritime_Militia.pdf" muted>AMTI / C4ADS, <em>Pulling Back the Curtain on China's Maritime Militia</em> (2021)</SrcLink> appendices ·
        CGA expulsions from <SrcLink href={enforcement?.cga_stats_home} muted>績效統計月報</SrcLink> <SrcLink href={t81?.source_url} muted>表8-1</SrcLink> ·
        Taiwan Bank box from the literature extent of the shoal. Map basemap: CartoDB Positron (&copy; OpenStreetMap contributors, &copy; CARTO).
      </p>
    </>
  );
}
