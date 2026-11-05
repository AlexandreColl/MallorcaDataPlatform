import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development /api goes to the REST API of the local stack; in the image nginx does the same (nginx.conf).
const apiTarget = process.env.API_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  // maplibre loads its worker from a file next to its module: pre-bundling it would break that URL.
  optimizeDeps: { exclude: ["maplibre-gl"] },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: apiTarget, rewrite: (path) => path.replace(/^\/api/, "") },
    },
  },
  build: {
    chunkSizeWarningLimit: 1200, // maplibre and echarts are big; each goes in its own chunk
    rollupOptions: {
      output: {
        manualChunks: (id) => (id.includes("maplibre-gl") ? "maplibre" : id.includes("echarts") ? "echarts" : undefined),
      },
    },
  },
});
