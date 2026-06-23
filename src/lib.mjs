import { chromium } from 'playwright';
import { readFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(__dirname, '..');
export const PROFILES_DIR = path.join(ROOT, 'profiles');
export const SCREENSHOTS_DIR = path.join(ROOT, 'screenshots');

export async function loadConfig() {
  const raw = await readFile(path.join(ROOT, 'config.json'), 'utf8').catch(() => {
    throw new Error('Нет config.json. Скопируй config.example.json -> config.json и заполни.');
  });
  return JSON.parse(raw);
}

// Папка постоянного профиля под конкретный аккаунт — здесь живёт залогиненная сессия Google.
export function profilePath(accountId) {
  return path.join(PROFILES_DIR, accountId);
}

// Открывает Chromium с постоянным профилем аккаунта (сессия сохраняется между запусками).
export async function openAccountBrowser(accountId, { headless = false } = {}) {
  await mkdir(profilePath(accountId), { recursive: true });
  const context = await chromium.launchPersistentContext(profilePath(accountId), {
    headless,
    viewport: { width: 1366, height: 850 },
    locale: 'ru-RU',
    args: ['--disable-blink-features=AutomationControlled'],
  });
  return context;
}

export function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

export function randomDelay(min, max) {
  return sleep(min + Math.floor(Math.random() * (max - min)));
}
