// Основной прогон: по каждому аккаунту отправляет на индексацию до dailyLimitPerAccount
// URL в день, с человекоподобными задержками. Ведёт state.json, чтобы не превышать
// дневной лимит и не слать один и тот же URL дважды за день.
//
// Запуск:
//   node src/run.mjs           -> все аккаунты
//   node src/run.mjs acc1      -> только конкретный аккаунт
//
// Повесь на расписание (cron / Планировщик задач) раз в сутки.

import {
  loadConfig, openAccountBrowser, randomDelay, ROOT,
  fingerprintFor, resolveProxy, rotateProxyIp, sleep,
} from './lib.mjs';
import { requestIndexing } from './gsc.mjs';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const STATE_FILE = path.join(ROOT, 'state.json');
const today = new Date().toISOString().slice(0, 10);

async function loadState() {
  return JSON.parse(await readFile(STATE_FILE, 'utf8').catch(() => '{}'));
}
async function saveState(state) {
  await writeFile(STATE_FILE, JSON.stringify(state, null, 2));
}

const only = process.argv[2];
const config = await loadConfig();
const limit = config.dailyLimitPerAccount ?? 10;
const min = config.minDelayMs ?? 8000;
const max = config.maxDelayMs ?? 20000;
const accounts = only ? config.accounts.filter((a) => a.id === only) : config.accounts;

const state = await loadState();

let firstAccount = true;
for (const acc of accounts) {
  const key = `${acc.id}:${today}`;
  const done = new Set(state[key]?.done || []);
  let submittedToday = done.size;

  const pending = (acc.urls || []).filter((u) => !done.has(u));
  const budget = Math.max(0, limit - submittedToday);

  console.log(`\n=== ${acc.id} (${acc.label || ''}) ===`);
  console.log(`Сегодня уже отправлено: ${submittedToday}/${limit}. В очереди: ${pending.length}. Лимит на сегодня: ${budget}.`);

  if (budget === 0 || pending.length === 0) {
    console.log('Пропуск — нечего отправлять.');
    continue;
  }

  // Между аккаунтами дёргаем ротацию мобильного IP (у каждого аккаунта — свой свежий IP),
  // но НЕ перед самым первым (его IP и так свежий) и держим IP стабильным внутри сессии.
  if (!firstAccount) await rotateProxyIp(config, console.log);
  firstAccount = false;
  // Случайный сдвиг старта, чтобы аккаунты не били в одну секунду.
  await sleep(Math.floor(Math.random() * 4000));

  const proxy = resolveProxy(config, acc);
  if (proxy) console.log(`   прокси: ${proxy.server}${proxy.username ? ' (auth)' : ''}`);
  const context = await openAccountBrowser(acc.id, {
    headless: config.headless ?? false,
    proxy,
    fingerprint: fingerprintFor(acc.id, config),
  });
  const page = context.pages()[0] || (await context.newPage());

  try {
    for (const url of pending.slice(0, budget)) {
      process.stdout.write(`-> ${url} ... `);
      const result = await requestIndexing(page, acc.property, url, { min, max });

      if (result === 'ok') {
        done.add(url);
        submittedToday++;
        state[key] = { done: [...done] };
        await saveState(state);
        console.log('OK');
      } else if (result === 'quota') {
        console.log('ЛИМИТ Google исчерпан — стоп по аккаунту');
        break;
      } else if (result === 'not_logged') {
        console.log('НЕ ЗАЛОГИНЕН — запусти: node src/login.mjs ' + acc.id);
        break;
      } else {
        console.log('ошибка (см. screenshots/) — пропускаю');
      }

      await randomDelay(min, max);
    }
  } finally {
    await context.close();
  }
}

console.log('\nГотово.');
process.exit(0);
