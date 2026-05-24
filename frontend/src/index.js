import ReactDOM from "react-dom/client";
import "./index.css";
import App from "./App";

// React.StrictMode removed for react-leaflet 4 compatibility:
// React 19's stricter dev double-mount trips Leaflet's "Map container
// is already initialized" guard before our cleanup can clear `_leaflet_id`.
// Strict Mode's checks are dev-only and weren't catching anything load-
// bearing here. Revisit if we migrate to a Strict-Mode-friendly map lib.
const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
