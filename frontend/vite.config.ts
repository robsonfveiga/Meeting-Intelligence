import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * The dev server proxies `/api` to the backend, so the browser only ever talks
 * to one origin. That is simpler than relying on the permissive CORS headers the
 * API sets for development, and it means the production build works behind any
 * reverse proxy without a rebuild.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Reachable from the host when this runs inside a container.
    host: true,
    proxy: {
      "/api": {
        target: process.env.API_ORIGIN ?? "http://localhost:8080",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  build: { outDir: "dist", sourcemap: true },
});
