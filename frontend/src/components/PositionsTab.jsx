import { useEffect, useState } from "react";
import { fetchPositions, patchPositionsText } from "../api";
import { PARTY_COLOURS } from "../partyColours";
import { READ_ONLY } from "../readOnly";

// Positions & Legal Status — curated reference page (content in
// scraper/processors/positions.json, served by /api/positions). Descriptive,
// not adjudicative: every block is an actor's STATED position with a dated
// source. Empty content fields render as "entry pending" placeholders while
// the entries are co-written.
//
// Admin build: every content block carries a ✎ opening an edit modal that
// PATCHes individual string fields back into the JSON file (the co-writing
// flow — wording is polished in the browser, structure/sources stay
// hand-curated). Structural keys are excluded here AND rejected server-side.

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

const PROSE = {
  fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--text-secondary)",
  lineHeight: 1.65, margin: 0,
};

function Pending() {
  return (
    <span style={{ ...PROSE, fontStyle: "italic", color: "var(--text-muted)" }}>
      Entry pending — being written.
    </span>
  );
}

// --- Inline editing (admin build only) --------------------------------------

// Structural / enum keys the edit modal never exposes (the server also
// rejects them — keep in lockstep with _PROTECTED_LEAVES in positions.py).
const EDIT_EXCLUDE = new Set(["id", "actor_id", "party", "depth", "iso"]);

function EditBtn({ onClick }) {
  if (!onClick) return null;
  return (
    <button
      onClick={onClick}
      title="Edit text"
      style={{
        background: "none", border: "none", cursor: "pointer", padding: "0 4px",
        fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-muted)",
      }}
    >
      ✎
    </button>
  );
}

function EditModal({ target, onSaved, onClose }) {
  const fields = Object.entries(target.obj).filter(
    ([k, v]) => typeof v === "string" && !EDIT_EXCLUDE.has(k)
  );
  const [draft, setDraft] = useState(Object.fromEntries(fields));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const changed = fields.filter(([k, v]) => draft[k] !== v);

  async function save() {
    setSaving(true);
    setError("");
    try {
      for (const [k] of changed) {
        // Sequential on purpose — each PATCH rewrites the file.
        await patchPositionsText([...target.basePath, k], draft[k]);
      }
      onSaved();
      onClose();
    } catch (e) {
      setError(e.message || "Save failed");
      setSaving(false);
    }
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 1000,
        display: "flex", alignItems: "center", justifyContent: "center", padding: "20px",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--bg-card)", border: "1px solid var(--border-color)",
          padding: "18px 20px", width: "min(680px, 100%)", maxHeight: "85vh", overflowY: "auto",
        }}
      >
        <div style={{
          fontFamily: "var(--font-mono)", fontSize: "11px", fontWeight: 600,
          letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-primary)",
          marginBottom: "14px",
        }}>
          Edit — {target.title}
        </div>
        {fields.map(([k, orig]) => (
          <div key={k} style={{ marginBottom: "12px" }}>
            <div style={{
              fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: draft[k] !== orig ? "#b8860b" : "var(--text-muted)",
              marginBottom: "4px",
            }}>
              {k.replace(/_/g, " ")}{draft[k] !== orig ? " · edited" : ""}
            </div>
            <textarea
              value={draft[k]}
              onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}
              rows={Math.max(1, Math.min(8, Math.ceil((draft[k] || "").length / 90)))}
              style={{
                width: "100%", boxSizing: "border-box", resize: "vertical",
                fontFamily: "var(--font-body)", fontSize: "13px", lineHeight: 1.5,
                color: "var(--text-primary)", background: "var(--bg-main, transparent)",
                border: "1px solid var(--border-color)", padding: "6px 8px",
              }}
            />
          </div>
        ))}
        {error && (
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--accent-red, #dc2626)", marginBottom: "10px" }}>
            {error}
          </div>
        )}
        <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}>
          <button
            onClick={onClose}
            disabled={saving}
            style={{
              fontFamily: "var(--font-mono)", fontSize: "11px", cursor: "pointer",
              background: "none", border: "1px solid var(--border-color)",
              color: "var(--text-muted)", padding: "6px 14px",
            }}
          >
            Cancel
          </button>
          <button
            onClick={save}
            disabled={saving || changed.length === 0}
            style={{
              fontFamily: "var(--font-mono)", fontSize: "11px",
              cursor: changed.length ? "pointer" : "default",
              background: changed.length ? "var(--text-primary)" : "var(--border-color)",
              border: "1px solid var(--text-primary)",
              color: "var(--bg-card)", padding: "6px 14px",
            }}
          >
            {saving ? "Saving…" : `Save${changed.length ? ` (${changed.length})` : ""}`}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------

// formulation_en (formulation_zh, romanisation) — the inline treatment for
// original-language formulations, the nuance-bearing part of the page.
function Formulation({ en, zh, rom }) {
  if (!en && !zh) return null;
  return (
    <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>
      {en}
      {zh && (
        <span style={{ fontWeight: 400, color: "var(--text-secondary)" }}>
          {" "}({zh}{rom ? <em>, {rom}</em> : null})
        </span>
      )}
    </span>
  );
}

function SourceLinks({ sources }) {
  if (!sources || sources.length === 0) return null;
  return (
    <div style={{ marginTop: "6px", display: "flex", flexWrap: "wrap", gap: "10px" }}>
      {sources.map((s, i) => (
        <a key={i} href={s.url} target="_blank" rel="noreferrer" style={{
          fontFamily: "var(--font-mono)", fontSize: "10px",
          color: "var(--text-muted)", textDecoration: "underline",
        }}>
          {s.label}{s.date ? ` (${s.date})` : ""}
        </a>
      ))}
    </div>
  );
}

function DateAnchor({ label, date, by }) {
  if (!date && !by) return null;
  return (
    <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)", marginTop: "6px" }}>
      {label} {date || "—"}{by ? ` · ${by}` : ""}
    </div>
  );
}

function SubHead({ children }) {
  return (
    <div style={{
      fontFamily: "var(--font-mono)", fontSize: "10px", fontWeight: 600,
      letterSpacing: "0.1em", textTransform: "uppercase",
      color: "var(--text-muted)", margin: "18px 0 8px",
    }}>
      {children}
    </div>
  );
}

function ItemBlock({ children, onEdit }) {
  return (
    <div style={{
      padding: "12px 14px", border: "1px solid var(--border-color)",
      background: "var(--bg-card)", marginBottom: "8px", position: "relative",
    }}>
      {onEdit && (
        <span style={{ position: "absolute", top: "8px", right: "8px" }}>
          <EditBtn onClick={onEdit} />
        </span>
      )}
      {children}
    </div>
  );
}

function LegalItem({ item, onEdit }) {
  return (
    <ItemBlock onEdit={onEdit}>
      <div style={{ marginBottom: "4px" }}>
        <Formulation en={item.title_en} zh={item.title_zh} rom={item.romanisation} />
      </div>
      <p style={PROSE}>{item.summary_en || <Pending />}</p>
      {item.not_say_en && (
        <p style={{ ...PROSE, marginTop: "8px" }}>
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: "0.05em",
            textTransform: "uppercase", color: "#b8860b", marginRight: "6px",
          }}>
            what it does not say
          </span>
          {item.not_say_en}
        </p>
      )}
      <DateAnchor label="in force since" date={item.effective_date} />
      <SourceLinks sources={item.sources} />
    </ItemBlock>
  );
}

function PositionItem({ item, onEdit }) {
  return (
    <ItemBlock onEdit={onEdit}>
      <div style={{ marginBottom: "4px" }}>
        <Formulation en={item.formulation_en} zh={item.formulation_zh} rom={item.romanisation} />
      </div>
      <p style={PROSE}>{item.position_en || <Pending />}</p>
      {item.nuance_en && (
        <p style={{ ...PROSE, marginTop: "8px" }}>
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: "0.05em",
            textTransform: "uppercase", color: "#b8860b", marginRight: "6px",
          }}>
            the nuance
          </span>
          {item.nuance_en}
        </p>
      )}
      <DateAnchor label="as stated" date={item.as_stated} by={item.stated_by} />
      <SourceLinks sources={item.sources} />
    </ItemBlock>
  );
}

function PartyChip({ party, label }) {
  const colour = PARTY_COLOURS[party] || "#6b7280";
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: "6px",
      fontFamily: "var(--font-mono)", fontSize: "10px", fontWeight: 600,
      color: "var(--text-primary)",
    }}>
      <span style={{ width: "10px", height: "10px", background: colour, display: "inline-block" }} />
      {label}
    </span>
  );
}

function MisconceptionItem({ item, onEdit }) {
  return (
    <ItemBlock onEdit={onEdit}>
      <p style={PROSE}>
        <span style={{
          fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: "0.05em",
          textTransform: "uppercase", color: "var(--accent-red, #dc2626)", marginRight: "6px",
        }}>
          often assumed
        </span>
        {item.myth_en || <Pending />}
      </p>
      <p style={{ ...PROSE, marginTop: "8px" }}>
        <span style={{
          fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: "0.05em",
          textTransform: "uppercase", color: "var(--text-primary)", marginRight: "6px",
        }}>
          the record
        </span>
        {item.actually_en || <Pending />}
      </p>
      <SourceLinks sources={item.sources} />
    </ItemBlock>
  );
}

function ActorCard({ actor, basePath, openEdit }) {
  const edit = openEdit
    ? (obj, subPath, title) => openEdit(obj, [...basePath, ...subPath], title)
    : null;
  return (
    <div style={{ marginBottom: "8px" }}>
      <SectionHeader right={
        <>
          {actor.name_zh}
          {edit && <EditBtn onClick={() => edit(actor, [], actor.name_en)} />}
        </>
      }>
        {actor.name_en}
      </SectionHeader>
      <p style={{ ...PROSE, maxWidth: "820px" }}>{actor.intro_en || <Pending />}</p>

      {actor.legal_foundation?.length > 0 && (
        <>
          <SubHead>Legal foundation</SubHead>
          {actor.legal_foundation.map((it, i) => (
            <LegalItem
              key={it.id}
              item={it}
              onEdit={edit && (() => edit(it, ["legal_foundation", i], it.title_en))}
            />
          ))}
        </>
      )}

      {actor.current_position?.length > 0 && (
        <>
          <SubHead>Current stated position</SubHead>
          {actor.current_position.map((it, i) => (
            <PositionItem
              key={it.id}
              item={it}
              onEdit={edit && (() => edit(it, ["current_position", i], it.formulation_en))}
            />
          ))}
        </>
      )}

      {actor.sub_positions?.length > 0 && (
        <>
          <SubHead>Party positions</SubHead>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "8px" }}>
            {actor.sub_positions.map((sp, spIdx) => (
              <div key={sp.id} style={{ padding: "12px 14px", border: "1px solid var(--border-color)", background: "var(--bg-card)" }}>
                <div style={{ marginBottom: "8px" }}>
                  <PartyChip party={sp.party} label={sp.label_en} />
                </div>
                {sp.items?.length > 0
                  ? sp.items.map((it, i) => (
                      <div key={it.id} style={{ marginBottom: "10px" }}>
                        <div style={{ marginBottom: "3px" }}>
                          <Formulation en={it.formulation_en} zh={it.formulation_zh} rom={it.romanisation} />
                          {edit && (
                            <EditBtn onClick={() => edit(it, ["sub_positions", spIdx, "items", i], `${sp.label_en} — ${it.formulation_en}`)} />
                          )}
                        </div>
                        <p style={PROSE}>{it.position_en || <Pending />}</p>
                        <DateAnchor label="as stated" date={it.as_stated} by={it.stated_by} />
                        <SourceLinks sources={it.sources} />
                      </div>
                    ))
                  : <Pending />}
              </div>
            ))}
          </div>
        </>
      )}

      {actor.misconceptions?.length > 0 && (
        <>
          <SubHead>Commonly misunderstood</SubHead>
          {actor.misconceptions.map((it, i) => (
            <MisconceptionItem
              key={it.id}
              item={it}
              onEdit={edit && (() => edit(it, ["misconceptions", i], "Misconception"))}
            />
          ))}
        </>
      )}
    </div>
  );
}

function BriefActorCard({ actor, basePath, openEdit }) {
  const edit = openEdit
    ? (obj, subPath, title) => openEdit(obj, [...basePath, ...subPath], title)
    : null;
  return (
    <div style={{ padding: "14px 16px", border: "1px solid var(--border-color)", background: "var(--bg-card)", minWidth: 0, position: "relative" }}>
      {edit && (
        <span style={{ position: "absolute", top: "8px", right: "8px" }}>
          <EditBtn onClick={() => edit(actor, [], actor.name_en)} />
        </span>
      )}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "8px" }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-primary)" }}>
          {actor.name_en}
        </span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-muted)", paddingRight: edit ? "18px" : 0 }}>
          {actor.name_zh}
        </span>
      </div>
      <p style={PROSE}>{actor.intro_en || <Pending />}</p>
      {actor.current_position?.map((it, i) => (
        <div key={it.id} style={{ marginTop: "10px" }}>
          <div style={{ marginBottom: "3px" }}>
            <Formulation en={it.formulation_en} zh={it.formulation_zh} rom={it.romanisation} />
            {edit && (
              <EditBtn onClick={() => edit(it, ["current_position", i], it.formulation_en)} />
            )}
          </div>
          <p style={PROSE}>{it.position_en || <Pending />}</p>
          <DateAnchor label="as stated" date={it.as_stated} by={it.stated_by} />
          <SourceLinks sources={it.sources} />
        </div>
      ))}
    </div>
  );
}

function ConceptBlock({ concept, basePath, openEdit }) {
  const edit = openEdit
    ? (obj, subPath, title) => openEdit(obj, [...basePath, ...subPath], title)
    : null;
  return (
    <div style={{ marginBottom: "22px" }}>
      <div style={{ marginBottom: "6px" }}>
        <Formulation en={concept.title_en} zh={concept.title_zh} rom={concept.romanisation} />
        {edit && <EditBtn onClick={() => edit(concept, [], concept.title_en)} />}
      </div>
      <p style={{ ...PROSE, maxWidth: "820px", marginBottom: "10px" }}>
        {concept.what_en || <Pending />}
      </p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "8px" }}>
        {concept.readings?.map((r, i) => (
          <div key={r.actor_id} style={{ padding: "12px 14px", border: "1px solid var(--border-color)", background: "var(--bg-card)", position: "relative" }}>
            {edit && (
              <span style={{ position: "absolute", top: "8px", right: "8px" }}>
                <EditBtn onClick={() => edit(r, ["readings", i], `${concept.title_en} — ${r.label_en}`)} />
              </span>
            )}
            <div style={{
              fontFamily: "var(--font-mono)", fontSize: "10px", fontWeight: 600,
              letterSpacing: "0.08em", textTransform: "uppercase",
              color: "var(--text-muted)", marginBottom: "6px",
            }}>
              {r.label_en}
            </div>
            {r.formulation_zh && (
              <div style={{ ...PROSE, color: "var(--text-primary)", marginBottom: "4px" }}>
                {r.formulation_zh}
              </div>
            )}
            <p style={PROSE}>{r.reading_en || <Pending />}</p>
            <SourceLinks sources={r.sources} />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function PositionsTab({ onOpenTab }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [editTarget, setEditTarget] = useState(null);

  const load = () => fetchPositions().then(setData).catch(() => setError(true));
  useEffect(() => {
    load();
  }, []);

  if (error) {
    return (
      <main style={{ padding: "28px 32px" }}>
        <p style={{ color: "var(--accent-red)", fontFamily: "var(--font-mono)", fontSize: "13px", padding: "40px 0" }}>
          Couldn't load positions content.
        </p>
      </main>
    );
  }
  if (!data) {
    return (
      <main style={{ padding: "28px 32px" }}>
        <p style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: "13px", padding: "40px 0" }}>
          Loading positions…
        </p>
      </main>
    );
  }

  // Keep each actor's ORIGINAL index — edit paths address the unfiltered
  // data.actors array, and full/brief is a filtered view of it.
  const actors = (data.actors || []).map((actor, idx) => ({ actor, idx }));
  const fullActors = actors.filter(({ actor }) => actor.depth === "full");
  const briefActors = actors.filter(({ actor }) => actor.depth === "brief");

  const openEdit = READ_ONLY
    ? null
    : (obj, basePath, title) => setEditTarget({ obj, basePath, title });

  return (
    <main style={{ padding: "28px 32px", minWidth: 0 }}>
      <SectionHeader right={
        <>
          {`last reviewed ${data._meta?.last_reviewed || "—"}`}
          {openEdit && <EditBtn onClick={() => openEdit(data._meta, ["_meta"], "Page meta")} />}
        </>
      }>
        Positions &amp; Legal Status
      </SectionHeader>

      <p style={{ ...PROSE, maxWidth: "820px", marginBottom: "18px" }}>
        What each side of the strait — and the powers around it —{" "}
        <strong style={{ color: "var(--text-primary)" }}>formally claims, and what it has actually said</strong>.
        Every entry below is a <em>stated</em> position anchored to a dated primary source:
        the statute, communiqué, or transcript itself. This page describes; it does not
        adjudicate. The distinctions here are routinely blurred in coverage — the
        difference between Washington's One China <em>policy</em> and Beijing's One China{" "}
        <em>principle</em>, or between what UN Resolution 2758 decided and what it is said
        to have decided, is where most cross-strait misreading starts.
      </p>

      {fullActors.map(({ actor, idx }) => (
        <ActorCard key={actor.id} actor={actor} basePath={["actors", idx]} openEdit={openEdit} />
      ))}

      {briefActors.length > 0 && (
        <>
          <SectionHeader>Other players</SectionHeader>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "10px" }}>
            {briefActors.map(({ actor, idx }) => (
              <BriefActorCard key={actor.id} actor={actor} basePath={["actors", idx]} openEdit={openEdit} />
            ))}
          </div>
        </>
      )}

      <SectionHeader>Contested concepts</SectionHeader>
      <p style={{ ...PROSE, maxWidth: "820px", marginBottom: "16px" }}>
        Terms that carry a different meaning depending on who is speaking — the
        disagreement over the term is itself the substance.
      </p>
      {(data.concepts || []).map((c, i) => (
        <ConceptBlock key={c.id} concept={c} basePath={["concepts", i]} openEdit={openEdit} />
      ))}

      <div style={{ margin: "26px 0 8px", fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--text-muted)" }}>
        For where the rest of the world stands on the Taiwan question, see the{" "}
        {onOpenTab ? (
          <button onClick={() => onOpenTab("diplomacy")} style={{
            background: "none", border: "none", padding: 0, cursor: "pointer",
            fontFamily: "inherit", fontSize: "inherit",
            color: "var(--text-primary)", textDecoration: "underline",
          }}>
            Diplomacy tracker
          </button>
        ) : (
          <span style={{ color: "var(--text-primary)" }}>Diplomacy tracker</span>
        )}
        {" "}— live third-country stances extracted from the corpus.
      </div>

      {editTarget && (
        <EditModal target={editTarget} onSaved={load} onClose={() => setEditTarget(null)} />
      )}
    </main>
  );
}
