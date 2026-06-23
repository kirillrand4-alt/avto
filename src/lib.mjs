import { chromium } from 'playwright';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(__dirname, '..');
export const PROFILES_DIR = path.join(ROOT, 'profiles');
export const SCREENSHOTS_DIR = path.join(ROOT, 'screenshots');
export const CONFIG_PATH = path.join(ROOT, 'config.json');
export const STATE_PATH = path.join(ROOT, 'state.json');

const DEFAULT_CONFIG = {
  dailyLimitPerAccount: 10,
  minDelayMs: 8000,
  maxDelayMs: 20000,
  headless: false,
  accounts: [],
};

export async function loadConfig() {
  const raw = await readFile(CONFIG_PATH, 'utf8').catch(() => null);
  if (raw == null) return { ...DEFAULT_CONFIG };
  return { ...DEFAULT_CONFIG, ...JSON.parse(raw) };
}

// Атомарная запись конфига (через временный файл) — чтобы не побить config.json при сбое.
export async function saveConfig(config) {
  const tmp = CONFIG_PATH + '.tmp';
  await writeFile(tmp, JSON.stringify(config, null, 2));
  const { rename } = await import('node:fs/promises');
  await rename(tmp, CONFIG_PATH);
}

// Сколько URL уже отправлено по аккаунту за сегодня (по state.json, который ведёт run.mjs).
export async function loadState() {
  const raw = await readFile(STATE_PATH, 'utf8').catch(() => '{}');
  return JSON.parse(raw);
}

export function todayKey() {
  return new Date().toISOString().slice(0, 10);
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
