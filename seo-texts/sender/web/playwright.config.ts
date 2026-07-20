import { defineConfig, devices } from "@playwright/test";

// Два веб-сервера: (1) сеет БД + поднимает FastAPI serve-api на :8099;
// (2) Vite dev на :5173 проксирует /api → :8099. Браузер — предустановленный
// Chromium (PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers).

const API_PORT = 8099;
const WEB_PORT = 5173;

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    trace: "retain-on-failure",
  },
  // Предустановленный Chromium: версия @playwright/test не совпадает с ревизией
  // в /opt/pw-browsers → указываем реальный бинарь напрямую (не скачивать).
  projects: [{
    name: "chromium",
    use: {
      ...devices["Desktop Chrome"],
      // chrome-headless-shell реализует old-headless, который передаёт PW 1.48
      // (полный chromium-1194 его убрал → падение при запуске).
      launchOptions: {
        executablePath: process.env.PW_CHROME
          || "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell",
      },
    },
  }],
  webServer: [
    {
      command: `E2E_API_PORT=${API_PORT} python3 e2e/seed_and_serve.py`,
      port: API_PORT,
      reuseExistingServer: false,
      timeout: 30_000,
      stdout: "pipe",
    },
    {
      command: `SENDER_API_URL=http://127.0.0.1:${API_PORT} npm run dev`,
      port: WEB_PORT,
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});
