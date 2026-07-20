import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// В dev API-запросы (/api/*) проксируются на локальный `python -m sender serve-api`
// (по умолчанию :8080). В проде SPA собирается в dist/ и раздаётся статикой
// (FastAPI StaticFiles или nginx) с тем же /api-префиксом на обратном прокси.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.SENDER_API_URL || "http://127.0.0.1:8080",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
  build: { outDir: "dist", sourcemap: true },
  test: {
    environment: "happy-dom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
  },
});
