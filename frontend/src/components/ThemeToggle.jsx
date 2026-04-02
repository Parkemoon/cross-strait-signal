import { useState, useEffect } from "react";

export default function ThemeToggle() {
  const [dark, setDark] = useState(() => {
    if (typeof window !== "undefined") {
      return window.matchMedia("(prefers-color-scheme: dark)").matches;
    }
    return true;
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  return (
    <button
      onClick={() => setDark(!dark)}
      style={{
        background: "var(--bg-card)",
        color: "var(--text-secondary)",
        border: "1px solid var(--border-color)",
        borderRadius: "6px",
        padding: "6px 12px",
        cursor: "pointer",
        fontSize: "14px",
      }}
    >
      {dark ? "☀ Light" : "● Dark"}
    </button>
  );
}