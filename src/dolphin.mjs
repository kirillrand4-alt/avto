// Коннектор к Dolphin{anty} через его Local API.
// Local API работает, пока запущено десктоп-приложение Dolphin (по умолчанию
// http://localhost:3001/v1.0). Профиль в Dolphin сам несёт прокси и отпечаток —
// мы только стартуем его и подключаемся к его Chromium по CDP.

import { chromium } from 'playwright';

const DEFAULT_BASE = 'http://localhost:3001/v1.0';

function apiBase(cfg) {
  return (cfg.dolphin?.apiBase || DEFAULT_BASE).replace(/\/$/, '');
}
function headers(cfg) {
  const h = { 'Content-Type': 'application/json' };
  if (cfg.dolphin?.token) h.Authorization = 'Bearer ' + cfg.dolphin.token;
  return h;
}

// Стартует профиль и возвращает подключённый Playwright Browser (через CDP).
export async function dolphinStart(cfg, profileId, { headless = false } = {}) {
  const url = `${apiBase(cfg)}/browser_profiles/${profileId}/start?automation=1${headless ? '&headless=1' : ''}`;
  const res = await fetch(url, { headers: headers(cfg), signal: AbortSignal.timeout(60000) });
  const data = await res.json().catch(() => ({}));
  const auto = data.automation;
  if (!auto?.port) {
    throw new Error(`Dolphin не стартовал профиль ${profileId}: ${JSON.stringify(data)}`);
  }
  const endpoint = auto.wsEndpoint
    ? `ws://127.0.0.1:${auto.port}${auto.wsEndpoint}`
    : `http://127.0.0.1:${auto.port}`;
  // Если подключение по CDP упало — профиль уже запущен, обязательно останавливаем его,
  // иначе он «висит» осиротевшим (утечка окна/ресурсов Dolphin).
  let browser;
  try { browser = await chromium.connectOverCDP(endpoint); }
  catch (e) { await dolphinStop(cfg, profileId); throw e; }
  return { browser, port: auto.port };
}

// Останавливает профиль Dolphin.
export async function dolphinStop(cfg, profileId) {
  const url = `${apiBase(cfg)}/browser_profiles/${profileId}/stop`;
  await fetch(url, { headers: headers(cfg), signal: AbortSignal.timeout(30000) }).catch(() => {});
}
