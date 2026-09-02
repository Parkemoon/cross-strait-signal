import { DocumentHeader, STANDFIRST } from "./documentChrome";
import CoastGuardSection from "./CoastGuardSection";
import { Copy } from "../copy";

// Maritime tab (Security › Maritime). Deliberately NOT under Military: coast
// guards are law-enforcement hulls, and grey-zone coercion works precisely
// because it stays below the military threshold. First section is the Coast
// Guard tracker (Phase 2e); the militia / dredger layer is queued to join it.

export default function MaritimeTab() {
  return (
    <main style={{ padding: "28px 32px", minWidth: 0 }}>
      <DocumentHeader
        eyebrow="Security · Maritime"
        title={<Copy k="maritime.title" as="span" fallback="Coast Guard Presence & Enforcement" />}
        standfirst={<Copy k="maritime.intro" as="p" style={STANDFIRST}
            fallback={"Coast Guard activity is one of the primary sources of direct contact between enforcement agencies from both sides of the strait."}  />}
        meta={"AIS presence · CGA enforcement"}
      />
      <CoastGuardSection />
    </main>
  );
}
