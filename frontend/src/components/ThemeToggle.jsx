import { useState, useEffect } from "react";

export default function ThemeToggle() {
  const [dark, setDark] = useState(() => {
    if (typeof window !== "undefined") {
      return window.matchMedia("(prefers-color-scheme: dark)").matches;
    }
    return false;
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  return (
    <button
      onClick={() => setDark(!dark)}
      style={{
        background: dark ? "#333" : "#e8e6e1",
        color: dark ? "#e8e6e1" : "#1c1c1c",
        border: "none",
        borderRadius: "20px",
        padding: "5px 14px",
        cursor: "pointer",
        fontSize: "12px",
        fontFamily: "var(--font-mono)",
        transition: "all 0.2s",
      }}
    >
      {dark ? "☀ Light" : "☽ Dark"}
    </button>
  );
}
