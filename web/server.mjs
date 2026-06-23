// Веб-панель управления автоиндексацией. Монтируется на BASE_PATH (по умолч. /avto),
// чтобы аккуратно жить за обратным прокси рядом с другими проектами parsercompressor.online.
//
// Возможности:
//   - управление аккаунтами и их списками URL (правит config.json);
//   - кнопки «Запустить прогон» и «Залогиниться» (запускают src/run.mjs / src/login.mjs);
//   - вход по логину/паролю (HTTP Basic);
//   - просмотр свежего лога прогона и дневных счётчиков.
//
// Запуск:  npm run web   (порт и пароль — в .env)

import express from 'express';
import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { timingSafeEqual } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  ROOT, SCREENSHOTS_DIR, loadConfig, saveConfig, loadState, todayKey,
} from '../src/lib.mjs';

// --- мини-загрузчик .env (без зависимостей) ---
async function loadEnv() {
  const txt = await readFile(path.join(ROOT, '.env'), 'utf8').catch(() => '');
  for (const line of txt.split('\n')) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/i);
    if (m && process.env[m[1]] === undefined) process.env[m[1]] = m[2].replace(/^["']|["']$/g, '');
  }
}
await loadEnv();

const PORT = parseInt(process.env.PORT || '8090', 10);
const HOST = process.env.HOST || '127.0.0.1';
const BASE = (process.env.BASE_PATH || '/avto').replace(/\/$/, '');
const USER = process.env.ADMIN_USER || 'admin';
const PASS = process.env.ADMIN_PASS || 'changeme';
const __dirname = path.dirname(fileURLToPath(import.meta.url));

// --- хранилище логов запусков (в памяти) ---
const jobs = new Map(); // accId|all -> { lines: [], running: bool, startedAt }

function startJob(jobKey, script, args) {
  if (jobs.get(jobKey)?.running) return jobs.get(jobKey);
  const job = { lines: [], running: true, startedAt: Date.now() };
  jobs.set(jobKey, job);
  const child = spawn(process.execPath, [path.join(ROOT, 'src', script), ...args], { cwd: ROOT });
  const push = (d) => {
    for (const l of d.toString().split('\n')) if (l.trim()) job.lines.push(l);
    if (job.lines.length > 500) job.lines.splice(0, job.lines.length - 500);
  };
  child.stdout.on('data', push);
  child.stderr.on('data', push);
  child.on('close', (code) => { job.running = false; job.lines.push(`--- завершено, код ${code} ---`); });
  child.on('error', (e) => { job.running = false; job.lines.push(`ОШИБКА запуска: ${e.message}`); });
  return job;
}

// --- встроенный планировщик (автопрогон раз в сутки в заданное время) ---
let lastAutoRun = null; // 'YYYY-MM-DD' последнего автозапуска — защита от двойного срабатывания
function startScheduler() {
  setInterval(async () => {
    try {
      const cfg = await loadConfig();
      const sch = cfg.schedule || {};
      if (!sch.enabled || !sch.time) return;
      const now = new Date();
      const hhmm = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
      const tk = todayKey();
      if (hhmm === sch.time && lastAutoRun !== tk && !jobs.get('all')?.running) {
        lastAutoRun = tk;
        console.log(`[scheduler] автопрогон в ${hhmm}`);
        startJob('all', 'run.mjs', []);
      }
    } catch (e) {
      console.error('[scheduler]', e.message);
    }
  }, 30000); // проверка каждые 30 сек
}

// --- авторизация (HTTP Basic) ---
function safeEq(a, b) {
  const ba = Buffer.from(a), bb = Buffer.from(b);
  return ba.length === bb.length && timingSafeEqual(ba, bb);
}
function auth(req, res, next) {
  const h = req.headers.authorization || '';
  const [, b64] = h.split(' ');
  if (b64) {
    const [u, p] = Buffer.from(b64, 'base64').toString().split(':');
    if (u && p && safeEq(u, USER) && safeEq(p, PASS)) return next();
  }
  res.set('WWW-Authenticate', 'Basic realm="avto"').status(401).send('Требуется вход');
}

// --- html ---
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function layout(body) {
  return `<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Авто-индексация GSC</title>
<style>
 body{font:15px/1.5 system-ui,Segoe UI,Arial;margin:0;background:#0f1115;color:#e6e6e6}
 .wrap{max-width:980px;margin:0 auto;padding:20px}
 h1{font-size:20px} h2{font-size:16px;margin:0}
 a{color:#6ea8fe} .muted{color:#8b93a1;font-size:13px}
 .card{background:#191c23;border:1px solid #262b36;border-radius:10px;padding:16px;margin:14px 0}
 .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;justify-content:space-between}
 input,textarea,button{font:inherit;border-radius:8px;border:1px solid #333a47;background:#0f1115;color:#e6e6e6;padding:8px 10px}
 textarea{width:100%;box-sizing:border-box;min-height:70px}
 button{background:#2b5cff;border-color:#2b5cff;cursor:pointer}
 button.sec{background:#262b36;border-color:#333a47}
 button.danger{background:#3a2330;border-color:#5a2a3a;color:#ff9aa9}
 form.inline{display:inline}
 .badge{display:inline-block;padding:2px 8px;border-radius:20px;background:#202531;font-size:12px;color:#9fb0c8}
 .url{font-size:13px;color:#cdd3dd;word-break:break-all}
 pre{background:#0b0d12;border:1px solid #20242e;border-radius:8px;padding:10px;overflow:auto;max-height:260px;font-size:12px}
 .grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
 label{display:block;font-size:13px;color:#9aa3b2;margin:6px 0 2px}
</style></head><body><div class="wrap">${body}</div></body></html>`;
}

// карточка настройки общего прокси
function proxyCard(p) {
  const isSocksAuth = /^socks/i.test(p.server || '') && (p.username || p.password);
  const warn = isSocksAuth
    ? `<div class="muted" style="color:#ffb86b;margin-top:6px">⚠ SOCKS5 с логином/паролем Chromium не поддерживает. Используй HTTP-эндпоинт прокси, либо whitelist IP сервера и убери логин/пароль.</div>`
    : '';
  return `<div class="card">
    <h2>Прокси (общий, мобильный)</h2>
    <span class="muted">Один прокси на все аккаунты. Между аккаунтами IP ротируется по ссылке, внутри сессии остаётся стабильным.</span>
    <form method="post" action="${BASE}/proxy">
      <label>Сервер (http://host:port или socks5://host:port)</label>
      <input name="server" value="${esc(p.server)}" style="width:100%;box-sizing:border-box" placeholder="http://89.39.105.78:11560">
      <div class="grid">
        <div><label>Логин (для HTTP-прокси)</label><input name="username" value="${esc(p.username)}"></div>
        <div><label>Пароль</label><input name="password" value="${esc(p.password)}"></div>
      </div>
      <label>Ссылка ротации IP (необязательно)</label>
      <input name="rotateUrl" value="${esc(p.rotateUrl)}" style="width:100%;box-sizing:border-box" placeholder="https://...rotate-link...">
      <div class="grid">
        <div><label>Локаль</label><input name="locale" value="${esc(p.locale || 'ru-RU')}"></div>
        <div><label>Таймзона</label><input name="timezone" value="${esc(p.timezone || 'Europe/Moscow')}"></div>
      </div>
      ${warn}
      <div style="margin-top:8px"><button class="sec">Сохранить прокси</button></div>
    </form>
  </div>`;
}

// карточка выбора движка браузера
function engineCard(cfg) {
  const engine = cfg.engine || 'builtin';
  const d = cfg.dolphin || {};
  return `<div class="card">
    <h2>Движок браузера</h2>
    <form method="post" action="${BASE}/engine">
      <label style="display:flex;align-items:center;gap:6px;margin:8px 0">
        <input type="radio" name="engine" value="builtin" ${engine === 'builtin' ? 'checked' : ''} style="width:auto">
        Встроенный Chromium (профиль + прокси + базовый отпечаток)
      </label>
      <label style="display:flex;align-items:center;gap:6px;margin:8px 0">
        <input type="radio" name="engine" value="dolphin" ${engine === 'dolphin' ? 'checked' : ''} style="width:auto">
        Dolphin{anty} (отпечаток и прокси — внутри профиля Dolphin)
      </label>
      <div class="grid">
        <div><label>Dolphin Local API</label><input name="apiBase" value="${esc(d.apiBase || 'http://localhost:3001/v1.0')}"></div>
        <div><label>API-токен Dolphin (если нужен)</label><input name="token" value="${esc(d.token || '')}"></div>
      </div>
      <div class="muted" style="margin-top:6px">Для Dolphin: запусти десктоп-приложение Dolphin на сервере, у каждого аккаунта укажи Profile ID. Окно профиля живёт в интерактивной сессии, не под службой.</div>
      <div style="margin-top:8px"><button class="sec">Сохранить движок</button></div>
    </form>
  </div>`;
}

const app = express();
app.use(express.urlencoded({ extended: true }));
app.set('trust proxy', true);

const r = express.Router();
r.use(auth);
r.use('/screenshots', express.static(SCREENSHOTS_DIR));

// главная
r.get('/', async (req, res) => {
  const cfg = await loadConfig();
  const state = await loadState();
  const tk = todayKey();
  const limit = cfg.dailyLimitPerAccount ?? 10;

  const accountsHtml = cfg.accounts.map((a) => {
    const sentToday = (state[`${a.id}:${tk}`]?.done || []).length;
    const job = jobs.get(a.id);
    const log = job ? `<pre>${esc(job.lines.slice(-40).join('\n'))}</pre>` : '';
    const urls = (a.urls || []).map((u, i) => `
      <div class="row" style="margin:4px 0">
        <span class="url">${esc(u)}</span>
        <form class="inline" method="post" action="${BASE}/accounts/${esc(a.id)}/urls/delete">
          <input type="hidden" name="index" value="${i}">
          <button class="danger" title="удалить">×</button>
        </form>
      </div>`).join('') || '<span class="muted">URL пока нет</span>';

    return `<div class="card">
      <div class="row">
        <h2>${esc(a.label || a.id)} <span class="muted">(${esc(a.id)})</span></h2>
        <span class="badge">сегодня: ${sentToday}/${limit}${job?.running ? ' · идёт прогон…' : ''}</span>
      </div>
      <div class="muted">свойство GSC: ${esc(a.property)}</div>
      <form class="inline" method="post" action="${BASE}/accounts/${esc(a.id)}/profile">
        <label style="display:inline">Dolphin Profile ID:</label>
        <input name="dolphinProfileId" value="${esc(a.dolphinProfileId || '')}" placeholder="напр. 123456" style="width:160px">
        <button class="sec">Сохранить ID</button>
      </form>
      <div style="margin:10px 0">${urls}</div>
      <form class="inline" method="post" action="${BASE}/accounts/${esc(a.id)}/urls">
        <input name="urls" placeholder="добавить URL (можно несколько через перевод строки)" style="width:60%">
        <button class="sec">+ URL</button>
      </form>
      <div class="row" style="margin-top:12px">
        <div>
          <form class="inline" method="post" action="${BASE}/accounts/${esc(a.id)}/run">
            <button ${job?.running ? 'disabled' : ''}>▶ Запустить прогон</button>
          </form>
          <form class="inline" method="post" action="${BASE}/accounts/${esc(a.id)}/login">
            <button class="sec" ${job?.running ? 'disabled' : ''}>🔑 Залогиниться</button>
          </form>
        </div>
        <form class="inline" method="post" action="${BASE}/accounts/${esc(a.id)}/delete"
              onsubmit="return confirm('Удалить аккаунт ${esc(a.id)}?')">
          <button class="danger">Удалить аккаунт</button>
        </form>
      </div>
      ${log}
    </div>`;
  }).join('');

  const sch = cfg.schedule || { enabled: false, time: '10:00' };
  const allJob = jobs.get('all');
  res.send(layout(`
    <div class="row"><h1>Авто-индексация GSC</h1>
      <span class="muted">лимит ${limit}/день · задержка ${cfg.minDelayMs}–${cfg.maxDelayMs} мс · ${cfg.headless ? 'headless' : 'видимый браузер'} · движок: ${esc(cfg.engine || 'builtin')}</span>
    </div>
    <div class="card">
      <div class="row"><h2>Аккаунты (${cfg.accounts.length})</h2>
        <form class="inline" method="post" action="${BASE}/run-all">
          <button ${allJob?.running ? 'disabled' : ''}>▶ Прогнать все${allJob?.running ? ' (идёт…)' : ''}</button>
        </form>
      </div>
    </div>
    <div class="card">
      <form method="post" action="${BASE}/schedule" class="row">
        <div>
          <h2>Автопрогон по расписанию</h2>
          <span class="muted">Раз в сутки запускает «Прогнать все». Работает, пока запущена панель (время сервера).${lastAutoRun ? ' Последний авто: ' + esc(lastAutoRun) : ''}</span>
        </div>
        <div class="row" style="gap:10px">
          <label style="display:flex;align-items:center;gap:6px;margin:0">
            <input type="checkbox" name="enabled" ${sch.enabled ? 'checked' : ''} style="width:auto"> включить
          </label>
          <input type="time" name="time" value="${esc(sch.time)}" style="width:auto">
          <button class="sec">Сохранить</button>
        </div>
      </form>
    </div>
    ${engineCard(cfg)}
    ${proxyCard(cfg.proxy || {})}
    ${accountsHtml || '<div class="card muted">Аккаунтов пока нет — добавь ниже.</div>'}
    <div class="card">
      <h2>Добавить аккаунт</h2>
      <form method="post" action="${BASE}/accounts">
        <div class="grid">
          <div><label>ID (латиницей, без пробелов)</label><input name="id" required placeholder="acc1"></div>
          <div><label>Подпись (например email)</label><input name="label" placeholder="mail@gmail.com"></div>
        </div>
        <label>Свойство в Search Console</label>
        <input name="property" required style="width:100%;box-sizing:border-box" placeholder="sc-domain:example.com  или  https://www.example.com/">
        <label>Dolphin Profile ID (только если движок Dolphin)</label>
        <input name="dolphinProfileId" placeholder="напр. 123456" style="width:100%;box-sizing:border-box">
        <label>URL (по одному в строке, необязательно)</label>
        <textarea name="urls" placeholder="https://example.com/page-1&#10;https://example.com/page-2"></textarea>
        <div style="margin-top:8px"><button>Добавить аккаунт</button></div>
      </form>
    </div>
    <p class="muted">Логин открывает видимый браузер на самом сервере — заходи на панель с того же ПК (Windows-десктоп), чтобы пройти вход в Google руками.</p>
  `));
});

function parseUrls(text) {
  return String(text || '').split(/\r?\n|,/).map((s) => s.trim()).filter(Boolean);
}
function findAcc(cfg, id) { return cfg.accounts.find((a) => a.id === id); }

// добавить аккаунт
r.post('/accounts', async (req, res) => {
  const cfg = await loadConfig();
  const id = String(req.body.id || '').trim();
  if (!id || findAcc(cfg, id)) return res.redirect(BASE + '/');
  cfg.accounts.push({
    id,
    label: String(req.body.label || '').trim(),
    property: String(req.body.property || '').trim(),
    dolphinProfileId: String(req.body.dolphinProfileId || '').trim(),
    urls: parseUrls(req.body.urls),
  });
  await saveConfig(cfg);
  res.redirect(BASE + '/');
});

// сохранить движок браузера
r.post('/engine', async (req, res) => {
  const cfg = await loadConfig();
  cfg.engine = req.body.engine === 'dolphin' ? 'dolphin' : 'builtin';
  cfg.dolphin = {
    apiBase: String(req.body.apiBase || 'http://localhost:3001/v1.0').trim(),
    token: String(req.body.token || '').trim(),
  };
  await saveConfig(cfg);
  res.redirect(BASE + '/');
});

// задать Dolphin Profile ID аккаунту
r.post('/accounts/:id/profile', async (req, res) => {
  const cfg = await loadConfig();
  const acc = findAcc(cfg, req.params.id);
  if (acc) { acc.dolphinProfileId = String(req.body.dolphinProfileId || '').trim(); await saveConfig(cfg); }
  res.redirect(BASE + '/');
});

// удалить аккаунт
r.post('/accounts/:id/delete', async (req, res) => {
  const cfg = await loadConfig();
  cfg.accounts = cfg.accounts.filter((a) => a.id !== req.params.id);
  await saveConfig(cfg);
  res.redirect(BASE + '/');
});

// добавить URL
r.post('/accounts/:id/urls', async (req, res) => {
  const cfg = await loadConfig();
  const acc = findAcc(cfg, req.params.id);
  if (acc) {
    acc.urls = acc.urls || [];
    for (const u of parseUrls(req.body.urls)) if (!acc.urls.includes(u)) acc.urls.push(u);
    await saveConfig(cfg);
  }
  res.redirect(BASE + '/');
});

// удалить URL
r.post('/accounts/:id/urls/delete', async (req, res) => {
  const cfg = await loadConfig();
  const acc = findAcc(cfg, req.params.id);
  if (acc) { acc.urls.splice(parseInt(req.body.index, 10), 1); await saveConfig(cfg); }
  res.redirect(BASE + '/');
});

// запустить прогон по аккаунту
r.post('/accounts/:id/run', (req, res) => {
  startJob(req.params.id, 'run.mjs', [req.params.id]);
  res.redirect(BASE + '/');
});

// логин в аккаунт (видимый браузер на сервере)
r.post('/accounts/:id/login', (req, res) => {
  startJob(req.params.id, 'login.mjs', [req.params.id]);
  res.redirect(BASE + '/');
});

// прогнать все
r.post('/run-all', (req, res) => {
  startJob('all', 'run.mjs', []);
  res.redirect(BASE + '/');
});

// сохранить прокси
r.post('/proxy', async (req, res) => {
  const cfg = await loadConfig();
  cfg.proxy = {
    server: String(req.body.server || '').trim(),
    username: String(req.body.username || '').trim(),
    password: String(req.body.password || '').trim(),
    rotateUrl: String(req.body.rotateUrl || '').trim(),
    locale: String(req.body.locale || 'ru-RU').trim(),
    timezone: String(req.body.timezone || 'Europe/Moscow').trim(),
  };
  await saveConfig(cfg);
  res.redirect(BASE + '/');
});

// сохранить расписание
r.post('/schedule', async (req, res) => {
  const cfg = await loadConfig();
  const time = String(req.body.time || '').match(/^\d{2}:\d{2}$/) ? req.body.time : (cfg.schedule?.time || '10:00');
  cfg.schedule = { enabled: !!req.body.enabled, time };
  await saveConfig(cfg);
  res.redirect(BASE + '/');
});

app.use(BASE, r);
app.get('/', (_req, res) => res.redirect(BASE + '/'));

app.listen(PORT, HOST, () => {
  console.log(`Панель: http://${HOST}:${PORT}${BASE}/  (за прокси — https://parsercompressor.online${BASE}/)`);
  startScheduler();
});
