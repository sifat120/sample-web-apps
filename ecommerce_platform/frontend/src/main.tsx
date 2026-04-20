/**
 * main.tsx — Application entry point.
 *
 * Vite loads /src/main.tsx via the <script type="module"> tag in index.html.
 * This file is responsible for:
 *   1. Importing the global Tailwind stylesheet so the @tailwind directives
 *      get compiled and injected into the page.
 *   2. Wrapping <App /> in <BrowserRouter> so any component can use react-router
 *      hooks (useNavigate, useLocation, etc.) and the <Link> / <Routes> tags.
 *   3. Mounting the React tree into the <div id="root"> element from index.html.
 *
 * StrictMode intentionally double-invokes effects in development to surface
 * subtle bugs (it has no effect in production builds).
 */

import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import "./index.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  // Fail loudly if index.html ever loses the #root mount point — easier to
  // debug than a silent blank page.
  throw new Error("Root element #root not found in index.html");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
