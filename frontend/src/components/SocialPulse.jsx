import { useState, useEffect } from "react";
import { fetchSocialPulse, correctSocialTranslation } from "../api";

function TranslationField({ item, onSaved }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(item.title_en_override || item.title_en || "");
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!value.trim()) return;
    setSaving(true);
    await correctSocialTranslation(item.id, value.trim());
    setSaving(false);
    setEditing(false);
    onSaved(item.id, value.trim());
  };

  const displayTranslation = item.title_en_override || item.title_en;
  const isOverridden = !!item.title_en_override;

  if (editing) {
    return (
      <div style={{ display: "flex", gap: "4px", alignItems: "center", marginTop: "2px" }}>
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSave()}
          style={{
            flex: 1,
            fontSize: "11px",
            padding: "2px 4px",
            background: "var(--bg-primary)",
            color: "var(--text-primary)",
            border: "1px solid var(--border-color)",
            borderRadius: "2px",
            fontFamily: "var(--font-mono)",
          }}
          autoFocus
        />
        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            fontSize: "10px",
            padding: "2px 6px",
            background: "#d97706",
            color: "#fff",
            border: "none",
            borderRadius: "2px",
            cursor: "pointer",
          }}
        >
          {saving ? "…" : "Save"}
        </button>
        <button
          onClick={() => setEditing(false)}
          style={{
            fontSize: "10px",
            padding: "2px 6px",
            background: "transparent",
            color: "var(--text-muted)",
            border: "1px solid var(--border-color)",
            borderRadius: "2px",
            cursor: "pointer",
          }}
        >
          Cancel
        </button>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "4px", marginTop: "2px" }}>
      <span style={{
        fontSize: "11px",
        color: isOverridden ? "var(--accent-yellow, #d97706)" : "var(--text-muted)",
        fontStyle: displayTranslation ? "normal" : "italic",
      }}>
        {displayTranslation || "translating…"}
      </span>
      {displayTranslation && (
        <button
          onClick={() => { setValue(displayTranslation); setEditing(true); }}
          title="Correct translation"
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "var(--text-muted)",
            fontSize: "10px",
            padding: "0 2px",
            lineHeight: 1,
          }}
        >
          ✎
        </button>
      )}
    </div>
  );
}

function WeiboItem({ item, onTranslationSaved }) {
  const highlight = item.is_cross_strait;

  return (
    <div style={{
      padding: "6px 0",
      borderBottom: "1px solid var(--border-color)",
      opacity: highlight ? 1 : 0.55,
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: "8px" }}>
        <span style={{
          background: highlight ? "#dc2626" : "var(--bg-primary)",
          color: highlight ? "#fff" : "var(--text-muted)",
          border: highlight ? "none" : "1px solid var(--border-color)",
          fontSize: "9px",
          fontWeight: 700,
          fontFamily: "var(--font-mono)",
          padding: "1px 4px",
          borderRadius: "2px",
          minWidth: "28px",
          textAlign: "center",
          flexShrink: 0,
          marginTop: "1px",
        }}>
          #{item.rank_position}
        </span>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: "13px", fontWeight: highlight ? 500 : 400, color: highlight ? "var(--text-primary)" : "var(--text-muted)" }}>
            {item.title}
          </div>
          <TranslationField item={item} onSaved={onTranslationSaved} />
          {item.heat_index > 0 && (
            <div style={{ fontSize: "10px", color: "var(--text-muted)", marginTop: "2px", fontFamily: "var(--font-mono)" }}>
              热度 {item.heat_index.toLocaleString()}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function PttItem({ item, onTranslationSaved }) {
  return (
    <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border-color)" }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: "8px" }}>
        <div style={{ flexShrink: 0, textAlign: "center", minWidth: "32px", marginTop: "1px" }}>
          <div style={{ fontSize: "10px", fontWeight: 700, color: "#16a34a", fontFamily: "var(--font-mono)" }}>
            ▲{item.push_count === 100 ? "爆" : item.push_count}
          </div>
          {item.boo_count > 0 && (
            <div style={{ fontSize: "10px", color: "#dc2626", fontFamily: "var(--font-mono)" }}>
              ▼{item.boo_count}
            </div>
          )}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "4px", flexWrap: "wrap" }}>
            <span style={{
              fontSize: "9px",
              fontFamily: "var(--font-mono)",
              fontWeight: 600,
              background: "var(--bg-primary)",
              border: "1px solid var(--border-color)",
              padding: "0 4px",
              borderRadius: "2px",
              color: "var(--text-muted)",
              flexShrink: 0,
            }}>
              {item.board}
            </span>
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ fontSize: "13px", fontWeight: 500, color: "var(--text-primary)", textDecoration: "none" }}
            >
              {item.title}
            </a>
          </div>
          <TranslationField item={item} onSaved={onTranslationSaved} />
        </div>
      </div>
    </div>
  );
}

export default function SocialPulse({ column = false }) {
  const [data, setData] = useState(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    fetchSocialPulse().then(setData).catch(() => {});
  }, []);

  if (!data) return null;

  const weiboItems = data.weibo?.items || [];
  const pttItems = data.ptt?.items || [];
  const hasWeibo = weiboItems.length > 0;
  const hasPtt = pttItems.length > 0;

  if (!hasWeibo && !hasPtt) return null;

  const handleTranslationSaved = (id, newTranslation) => {
    setData((prev) => {
      const updateItems = (items) =>
        items.map((item) =>
          item.id === id ? { ...item, title_en_override: newTranslation, title_en: item.title_en } : item
        );
      return {
        ...prev,
        weibo: { ...prev.weibo, items: updateItems(prev.weibo.items) },
        ptt: { ...prev.ptt, items: updateItems(prev.ptt.items) },
      };
    });
  };

  const formatTime = (ts) => {
    if (!ts) return null;
    try {
      return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch {
      return null;
    }
  };

  const crossStraitItems = weiboItems.filter(i => i.is_cross_strait);
  const crossStraitCount = crossStraitItems.length;

  // Shared section content
  const weiboSection = (
    <>
      <div style={{
        fontSize: "10px", fontFamily: "var(--font-mono)", fontWeight: 700,
        letterSpacing: "0.06em", color: "#dc2626", marginBottom: "4px", textTransform: "uppercase",
      }}>
        PRC · Weibo 微博热搜
      </div>
      {crossStraitItems.length > 0 ? (
        crossStraitItems.map((item) => (
          <WeiboItem key={item.id} item={item} onTranslationSaved={handleTranslationSaved} />
        ))
      ) : (
        <div style={{ color: "var(--text-muted)", fontSize: "12px", fontStyle: "italic", paddingTop: "8px" }}>
          {hasWeibo ? "No cross-strait related topics in top 50 trending" : "No data yet"}
        </div>
      )}
    </>
  );

  const pttSection = (
    <>
      <div style={{
        fontSize: "10px", fontFamily: "var(--font-mono)", fontWeight: 700,
        letterSpacing: "0.06em", color: "#1d4ed8", marginBottom: "4px", textTransform: "uppercase",
      }}>
        TW · PTT 批踢踢
      </div>
      {hasPtt ? (
        pttItems.map((item) => (
          <PttItem key={item.id} item={item} onTranslationSaved={handleTranslationSaved} />
        ))
      ) : (
        <div style={{ color: "var(--text-muted)", fontSize: "12px", fontStyle: "italic", paddingTop: "8px" }}>
          No high-engagement posts found
        </div>
      )}
    </>
  );

  // Column mode: always expanded, vertical stack, no card wrapper
  if (column) {
    return (
      <>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: "12px" }}>
          <h3 style={{
            fontFamily: "var(--font-headline)", fontSize: "13px", fontWeight: 600,
            letterSpacing: "0.08em", textTransform: "uppercase", color: "#d97706", margin: 0,
          }}>
            Social Pulse
          </h3>
          <span style={{ fontSize: "10px", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
            {`${crossStraitCount} · ${pttItems.length}`}
          </span>
        </div>
        <div style={{ paddingBottom: "24px", borderBottom: "1px solid var(--border-color)", marginBottom: "20px" }}>
          {weiboSection}
        </div>
        <div>
          {pttSection}
        </div>
      </>
    );
  }

  // Default inline mode: collapsible, two-column panel
  return (
    <div style={{ marginBottom: "32px" }}>
      <div
        onClick={() => setExpanded(e => !e)}
        style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: expanded ? "8px" : "0", cursor: "pointer", userSelect: "none" }}
      >
        <h3 style={{
          fontFamily: "var(--font-headline)", fontSize: "13px", fontWeight: 600,
          letterSpacing: "0.08em", textTransform: "uppercase", color: "#d97706", margin: 0,
          display: "flex", alignItems: "center", gap: "6px",
        }}>
          Social Pulse
          <span style={{ fontSize: "10px", fontWeight: 400, color: "var(--text-muted)", letterSpacing: 0, textTransform: "none" }}>
            {`Weibo ${crossStraitCount} · PTT ${pttItems.length}`}
          </span>
        </h3>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "10px", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
            Weibo {formatTime(data.weibo?.last_updated)}
            {data.ptt?.last_updated && ` · PTT ${formatTime(data.ptt?.last_updated)}`}
          </span>
          <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>{expanded ? "▲" : "▼"}</span>
        </div>
      </div>

      {expanded && (
        <div style={{
          display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0",
          background: "var(--bg-card)", border: "1px solid var(--border-color)",
          borderTop: "3px solid #d97706", borderRadius: "4px", overflow: "hidden",
        }}>
          <div style={{ padding: "12px 16px", borderRight: "1px solid var(--border-color)" }}>
            {weiboSection}
          </div>
          <div style={{ padding: "12px 16px" }}>
            {pttSection}
          </div>
        </div>
      )}
    </div>
  );
}
