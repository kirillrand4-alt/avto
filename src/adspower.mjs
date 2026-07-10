// Коннектор к AdsPower через его Local API.
// Local API работает, пока запущено приложение AdsPower (по умолчанию
// http://local.adspower.net:50325). Профиль AdsPower сам несёт прокси и отпечаток —
// мы стартуем его и подключаемся к Chromium по CDP.
//
// Важно: AdsPower просит не чаще ~1 запроса в секунду — поэтому небольшие паузы.

import { chromium } from 'playwright';

const DEFAULT_BASE = 'http://local.adspower.net:50325';

function apiBase(cfg) {
  return (cfg.adspower?.apiBase || DEFAULT_BASE).replace(/\/$/, '');
}
const pause = () => new Promise((r) => setTimeout(r, 1200));

// Стартует профиль и возвращает подключённый Playwright Browser (через CDP).
export async function adspowerStart(cfg, userId, { headless = false } = {}) {
  await pause();
  const url = `${apiBase(cfg)}/api/v1/browser/start?user_id=${encodeURIComponent(userId)}&headless=${headless ? 1 : 0}`;
  const res = await fetch(url, { signal: AbortSignal.timeout(60000) });
  const j = await res.json().catch(() => ({}));
  const ws = j?.data?.ws?.puppeteer;
  if (j.code !== 0 || !ws) {
    throw new Error(`AdsPower не стартовал профиль ${userId}: ${j.msg || JSON.stringify(j)}`);
  }
  // Если подключение по CDP упало — профиль уже запущен, останавливаем его,
  // иначе останется осиротевший браузер AdsPower (утечка).
  let browser;
  try { browser = await chromium.connectOverCDP(ws); }
  catch (e) { await adspowerStop(cfg, userId).catch(() => {}); throw e; }
  return { browser };
}

// Останавливает профиль AdsPower.
export async function adspowerStop(cfg, userId) {
  await pause();
  const url = `${apiBase(cfg)}/api/v1/browser/stop?user_id=${encodeURIComponent(userId)}`;
  await fetch(url, { signal: AbortSignal.timeout(30000) }).catch(() => {});
}
