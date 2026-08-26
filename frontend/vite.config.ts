import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import tsConfigPaths from "vite-tsconfig-paths";
import { tanstackRouter } from "@tanstack/router-plugin/vite";

// Static SPA served same-origin by Django (ADR 0003, ADR 0005).
// TanStack *Router* only — no Start, no Nitro, no Cloudflare.
export default defineConfig({
  plugins: [
    tanstackRouter({ target: "react", autoCodeSplitting: true }),
    react(),
    tailwindcss(),
    tsConfigPaths(),
  ],

  // Django serves the build from /static/app/ via Whitenoise.
  base: "/static/app/",

  build: {
    outDir: "../src/static/app",
    emptyOutDir: true,
    // Django's ManifestStaticFilesStorage does its own hashing in production;
    // Vite's content hashes are what actually bust caches.
    sourcemap: false,
  },

  server: {
    port: 5173,
    // Dev only. The browser sees one origin, so session cookies and CSRF work
    // exactly as they will in production.
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: false },
      "/media": { target: "http://127.0.0.1:8000", changeOrigin: false },
      "/admin": { target: "http://127.0.0.1:8000", changeOrigin: false },
    },
  },
});
