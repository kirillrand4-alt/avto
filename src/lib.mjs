import { chromium } from 'playwright';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import net from 'node:net';
import http from 'node:http';
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
  // Встроенный планировщик панели: автопрогон всех аккаунтов раз в сутки.
  schedule: { enabled: false, time: '10:00' },
  // Движок браузера: 'builtin' (наш Chromium + прокси) или 'dolphin' (Dolphin{anty}).
  engine: 'builtin',
  dolphin: { apiBase: 'http://localhost:3001/v1.0', token: '' },
  adspower: { apiBase: 'http://local.adspower.net:50325' },
  // Защита: на builtin без рабочего прокси запуск блокируется (чтобы не светить реальный
  // IP сервера и не палить аккаунты). Поставь true только для осознанного теста без прокси.
  allowNoProxy: false,
  // Общий (мобильный) прокси для всех аккаунтов.
  //   server   — 'http://host:port' или 'socks5://host:port'
  //   username/password — для HTTP-прокси (SOCKS5 с авторизацией Chromium НЕ умеет —
  //                       для SOCKS5 используй whitelist IP и оставь пустыми)
  //   rotateUrl — ссылка ротации IP (дёргается между аккаунтами); необязательно
  //   locale/timezone — база для отпечатка (можно переопределить у аккаунта)
  proxy: { server: '', username: '', password: '', rotateUrl: '', locale: 'ru-RU', timezone: 'Europe/Moscow' },
  accounts: [],
};

// --- пул для отпечатков: реалистичные десктопные Chrome на Win/Mac ---
const UA_POOL = [
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
];
const VIEWPORTS = [
  { width: 1366, height: 768 }, { width: 1440, height: 900 },
  { width: 1536, height: 864 }, { width: 1600, height: 900 }, { width: 1920, height: 1080 },
];

// Детерминированный отпечаток на аккаунт (стабилен между запусками для одного id).
export function fingerprintFor(accountId, cfg = {}) {
  const h = createHash('sha256').update(accountId).digest();
  const px = cfg.proxy || {};
  return {
    userAgent: UA_POOL[h[0] % UA_POOL.length],
    viewport: VIEWPORTS[h[1] % VIEWPORTS.length],
    locale: px.locale || 'ru-RU',
    timezoneId: px.timezone || 'Europe/Moscow',
  };
}

// Собирает proxy-опцию Playwright из конфига (общий прокси + возможный override у аккаунта).
// Chromium НЕ принимает логин/пароль внутри URL прокси — их надо отдавать отдельными
// полями. Поэтому если креды зашиты в server (http://user:pass@host:port) — вытаскиваем их.
export function resolveProxy(cfg = {}, acc = {}) {
  const g = cfg.proxy || {};
  const a = acc.proxy || {};
  let server = (a.server || g.server || '').trim();
  if (!server) return null;
  let username = (a.username ?? g.username ?? '').trim();
  let password = (a.password ?? g.password ?? '').trim();
  try {
    const u = new URL(server);
    if (u.username && !username) username = decodeURIComponent(u.username);
    if (u.password && !password) password = decodeURIComponent(u.password);
    u.username = '';
    u.password = '';
    server = u.toString().replace(/\/$/, ''); // server без userinfo и хвостового слэша
  } catch { /* строка без схемы — оставляем как есть */ }
  const opt = { server };
  if (username) opt.username = username;
  if (password) opt.password = password;
  return opt;
}

// Проверяет, что прокси реально работает: HTTP-прокси -> тянет внешний IP через него
// (возвращает строку IP), SOCKS -> проверяет TCP-доступность. null = прокси не отвечает.
// Нужно как предохранитель: не запускать аккаунт, если прокси мёртв (иначе риск голого IP).
export function checkProxy(proxyOpt, timeout = 15000) {
  return new Promise((resolve) => {
    if (!proxyOpt?.server) return resolve(null);
    let u;
    try { u = new URL(proxyOpt.server); } catch { return resolve(null); }
    const host = u.hostname;
    const port = parseInt(u.port, 10) || 80;
    if (/^socks/i.test(u.protocol)) {
      const s = net.connect(port, host);
      const done = (ok) => { s.destroy(); resolve(ok ? '(socks доступен)' : null); };
      s.on('connect', () => done(true));
      s.on('error', () => done(false));
      s.setTimeout(timeout, () => done(false));
      return;
    }
    const headers = { Host: 'api.ipify.org', Connection: 'close' };
    if (proxyOpt.username) {
      headers['Proxy-Authorization'] = 'Basic ' +
        Buffer.from(`${proxyOpt.username}:${proxyOpt.password || ''}`).toString('base64');
    }
    const req = http.request({ host, port, method: 'GET', path: 'http://api.ipify.org/', headers, timeout }, (res) => {
      let d = '';
      res.on('data', (c) => (d += c));
      res.on('end', () => {
        // Живым считаем прокси ТОЛЬКО при 2xx и теле, похожем на IP. Иначе 407 (нужна авторизация),
        // 5xx или HTML-страница ошибки прокси прошли бы как «рабочий прокси» и аккаунт стартовал бы.
        const body = d.trim();
        resolve(res.statusCode >= 200 && res.statusCode < 300 && /^[0-9a-f:.]+$/i.test(body) ? body : null);
      });
      res.on('error', () => resolve(null));
    });
    req.on('error', () => resolve(null));
    req.on('timeout', () => { req.destroy(); resolve(null); });
    req.end();
  });
}

// Дёргает ссылку ротации мобильного IP (между аккаунтами). Тихо игнорирует ошибки.
export async function rotateProxyIp(cfg = {}, log = () => {}) {
  const url = (cfg.proxy?.rotateUrl || '').trim();
  if (!url) return;
  try {
    const ctrl = AbortSignal.timeout(15000);
    await fetch(url, { signal: ctrl });
    log('   ↻ IP ротирован, жду стабилизации…');
    await sleep(5000);
  } catch (e) {
    log('   ! ротация IP не удалась: ' + e.message);
  }
}

export async function loadConfig() {
  const raw = await readFile(CONFIG_PATH, 'utf8').catch(() => null);
  if (raw == null) return { ...DEFAULT_CONFIG };
  // НЕ откатываемся молча на DEFAULT_CONFIG при битом JSON: пустой список аккаунтов мог бы
  // затем перезаписать реальный config.json. Явная ошибка — чтобы файл починили руками.
  let parsed;
  try { parsed = JSON.parse(raw); }
  catch (e) { throw new Error('config.json невалиден (' + e.message + '). Почини файл вручную.'); }
  return { ...DEFAULT_CONFIG, ...parsed };
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
  // Битый state.json (например, оборванная запись) НЕ должен ронять панель/прогон —
  // читаем как пустой (дневные счётчики сбросятся, но процесс выживет).
  try { return JSON.parse(raw); }
  catch { console.warn('   ! state.json повреждён — читаю как пустой'); return {}; }
}

export function todayKey() {
  return new Date().toISOString().slice(0, 10);
}

// Папка постоянного профиля под конкретный аккаунт — здесь живёт залогиненная сессия Google.
export function profilePath(accountId) {
  return path.join(PROFILES_DIR, accountId);
}

// Открывает Chromium с постоянным профилем аккаунта (сессия сохраняется между запусками).
// proxy — опция Playwright { server, username?, password? } (или null).
// fingerprint — { userAgent, viewport, locale, timezoneId } для разнесения отпечатков.
export async function openAccountBrowser(accountId, { headless = false, proxy = null, fingerprint = null } = {}) {
  await mkdir(profilePath(accountId), { recursive: true });
  const fp = fingerprint || {};
  const opts = {
    headless,
    viewport: fp.viewport || { width: 1366, height: 768 },
    locale: fp.locale || 'ru-RU',
    timezoneId: fp.timezoneId || 'Europe/Moscow',
    args: [
      '--disable-blink-features=AutomationControlled',
      // не давать WebRTC сливать реальный IP мимо прокси
      '--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
    ],
  };
  if (fp.userAgent) opts.userAgent = fp.userAgent;
  if (proxy) opts.proxy = proxy;
  const context = await chromium.launchPersistentContext(profilePath(accountId), opts);
  // Стелс: маскируем главные признаки автоматизации (что обычно палит наш Chromium).
  await context.addInitScript(() => {
    try {
      Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
      Object.defineProperty(navigator, 'languages', { get: () => ['ru-RU', 'ru'] });
      Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
      window.chrome = window.chrome || { runtime: {} };
      const q = navigator.permissions && navigator.permissions.query;
      if (q) {
        navigator.permissions.query = (p) =>
          p && p.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : q(p);
      }
    } catch { /* не валим страницу из-за стелса */ }
  });
  return context;
}

export function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

export function randomDelay(min, max) {
  return sleep(min + Math.floor(Math.random() * (max - min)));
}
