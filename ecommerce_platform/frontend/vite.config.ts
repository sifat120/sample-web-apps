import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Vite configuration for the e-commerce frontend.
 *
 * The proxy section is the key piece: any request starting with /api is
 * forwarded to the FastAPI backend at localhost:8000, with /api stripped off.
 *
 * Example:
 *   Frontend calls:  fetch("/api/products/search?q=boots")
 *   Backend receives: GET /products/search?q=boots
 *
 * This avoids CORS issues during local development — both the frontend
 * (port 5173) and the backend (port 8000) appear to be the same origin
 * from the browser's perspective.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        // Strip the /api prefix before forwarding to the backend
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
