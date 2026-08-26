import { SectionHeader } from "./MilitaryTab";
import CoastGuardSection from "./CoastGuardSection";

// Maritime tab (Security › Maritime). Deliberately NOT under Military: coast
// guards are law-enforcement hulls, and grey-zone coercion works precisely
// because it stays below the military threshold. First section is the Coast
// Guard tracker (Phase 2e); the militia / dredger layer is queued to join it.
export default function MaritimeTab() {
  return (
    <main style={{ padding: "28px 32px", minWidth: 0 }}>
      <SectionHeader right="AIS presence · CGA enforcement">
        Coast Guard Presence &amp; Enforcement
      </SectionHeader>
      <p style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--text-secondary)", lineHeight: 1.55, margin: "0 0 14px" }}>
        Law-enforcement vessels, not warships. Coast guards are the instrument of choice on both sides of the
        strait because their presence asserts jurisdiction without crossing a military threshold — which is why
        this tracker lives beside the PLA section, not inside it.
      </p>
      <CoastGuardSection />
    </main>
  );
}
