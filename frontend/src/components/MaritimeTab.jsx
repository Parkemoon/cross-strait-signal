import { SectionHeader } from "./MilitaryTab";
import CoastGuardSection from "./CoastGuardSection";
import { Copy } from "../copy";

// Maritime tab (Security › Maritime). Deliberately NOT under Military: coast
// guards are law-enforcement hulls, and grey-zone coercion works precisely
// because it stays below the military threshold. First section is the Coast
// Guard tracker (Phase 2e); the militia / dredger layer is queued to join it.
const INTRO = { fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--text-secondary)", lineHeight: 1.55, margin: "0 0 14px" };

export default function MaritimeTab() {
  return (
    <main style={{ padding: "28px 32px", minWidth: 0 }}>
      <SectionHeader right="AIS presence · CGA enforcement">
        Coast Guard Presence &amp; Enforcement
      </SectionHeader>
      <Copy k="maritime.intro" style={INTRO}
            fallback={"Law-enforcement vessels, not warships — coast guards assert jurisdiction without crossing a military threshold."} />
      <CoastGuardSection />
    </main>
  );
}
