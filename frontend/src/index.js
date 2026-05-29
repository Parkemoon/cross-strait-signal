import ReactDOM from "react-dom/client";
import "./index.css";
import App from "./App";
import { READ_ONLY } from "./readOnly";

// Umami analytics — public build only. Injected at runtime rather than in
// public/index.html because that template feeds both the admin and public
// bundles; we don't want analyst sessions counted. Cookieless / privacy-
// friendly, so no consent banner needed.
if (READ_ONLY) {
  const umami = document.createElement("script");
  umami.defer = true;
  umami.src = "https://analytics.strait-signal.net/script.js";
  umami.setAttribute("data-website-id", "f7012415-3e06-4242-85af-023c157623be");
  document.head.appendChild(umami);
}

// React.StrictMode removed for react-leaflet 4 compatibility:
// React 19's stricter dev double-mount trips Leaflet's "Map container
// is already initialized" guard before our cleanup can clear `_leaflet_id`.
// Strict Mode's checks are dev-only and weren't catching anything load-
// bearing here. Revisit if we migrate to a Strict-Mode-friendly map lib.
const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
