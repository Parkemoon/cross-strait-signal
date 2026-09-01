import { useState, useEffect } from "react";

// ☾/☀ theme toggle. Resolves a `system` preference via prefers-color-scheme
// on mount (dark by default on a dark system); persists only an explicit
// choice to localStorage, so users who never touch it keep following their
// OS. Sets both the `.dark` class (token overrides in index.css) and
// `data-theme` on <html>.
const STORAGE_KEY = "css-theme";

function initialDark() {
  if (typeof window === "undefined") return false;
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === "dark") return true;
    if (saved === "light") return false;
  } catch (e) { /* private mode etc. — fall through to system */ }
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export default function ThemeToggle() {
  const [dark, setDark] = useState(initialDark);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  }, [dark]);

  const choose = (next) => {
    setDark(next);
    try { window.localStorage.setItem(STORAGE_KEY, next ? "dark" : "light"); } catch (e) { /* ignore */ }
  };

  return (
    <button
      onClick={() => choose(!dark)}
      title={dark ? "Switch to light" : "Switch to dark"}
      style={{
        background: "none",
        color: "var(--faint)",
        border: "1px solid var(--hair)",
        padding: "2px 9px",
        cursor: "pointer",
        fontSize: "12px",
        lineHeight: 1.6,
        fontFamily: "var(--font-mono)",
        userSelect: "none",
      }}
    >
      {dark ? "☀" : "☾"}
    </button>
  );
}
