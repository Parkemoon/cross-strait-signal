// Wraps the lazily loaded section views (App.js). Suspense shows a line while
// the view's chunk downloads; the error boundary covers the case where it
// can't. Every build renames the chunks, so a page left open across a deploy
// asks for files that no longer exist, and a reload fetches the new index.
// Keyed on the view, so picking another tab clears a failure.
import { Component, Suspense } from "react";
import { Btn } from "./adminChrome";

// Same line the tabs show while their own data loads.
const LINE = {
  fontFamily: "var(--font-mono)",
  fontSize: "13px",
  color: "var(--text-muted)",
  margin: 0,
};

class ViewErrorBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error) {
    console.error("Failed to load view:", error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div style={{ padding: "28px 32px" }}>
        <p style={{ ...LINE, marginBottom: "12px" }}>
          This section failed to load. Reload the page to try again.
        </p>
        <Btn onClick={() => window.location.reload()}>Reload</Btn>
      </div>
    );
  }
}

export default function ViewBoundary({ view, children }) {
  return (
    <ViewErrorBoundary key={view}>
      <Suspense fallback={<p style={{ ...LINE, padding: "28px 32px" }}>Loading…</p>}>
        {children}
      </Suspense>
    </ViewErrorBoundary>
  );
}
