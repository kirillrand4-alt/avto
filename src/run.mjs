// Основной прогон: по каждому аккаунту отправляет на индексацию до dailyLimitPerAccount
// URL в день, с человекоподобными задержками. Ведёт state.json, чтобы не превышать
// дневной лимит и не слать один и тот же URL дважды за день.
//
// Запуск:
//   node src/run.mjs           -> все аккаунты
//   node src/run.mjs acc1      -> только конкретный аккаунт
//
// Повесь на расписание (cron / Планировщик задач) раз в сутки.

import { loadConfig, randomDelay, ROOT, rotateProxyIp, sleep, resolveProxy, checkProxy } from './lib.mjs';
import { openSession, antidetectId } from './session.mjs';
import { requestIndexing } from './gsc.mjs';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const STATE_FILE = path.join(ROOT, 'state.json');
const today = new Date().toISOString().slice(0, 10);

async function loadState() {
  const raw = await readFile(STATE_FILE, 'utf8').catch(() => '{}');
  // Битый state.json не должен ронять прогон на старте — читаем как пустой.
  try { return JSON.parse(raw); }
  catch { console.warn('   ! state.json повреждён — читаю как пустой'); return {}; }
}
async function saveState(state) {
  // Атомарно (temp + rename), как saveConfig: обрыв записи не оставит битый файл,
  // который потом навсегда ронял бы все прогоны.
  const tmp = STATE_FILE + '.tmp';
  await writeFile(tmp, JSON.stringify(state, null, 2));
  const { rename } = await import('node:fs/promises');
  await rename(tmp, STATE_FILE);
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
  // «Отправлено сегодня» — число РЕАЛЬНЫХ обращений к Google (ok + unknown), а не только
  // успешных: unknown тоже тратит слот квоты. Иначе несколько прогонов за сутки (кнопка
  // «Прогнать» + планировщик) в сумме превысили бы dailyLimitPerAccount.
  let sentToday = state[key]?.sent ?? done.size;

  // Неоднозначные URL (клик прошёл, но подтверждения не увидели) храним под НЕ-датовым ключом,
  // чтобы исключение не сбрасывалось на следующий день и мы не переотправляли их, жгя квоту.
  const ambKey = `${acc.id}:ambiguous`;
  const ambiguous = new Set(state[ambKey]?.urls || []);

  const pending = (acc.urls || []).filter((u) => !done.has(u) && !ambiguous.has(u));
  const budget = Math.max(0, limit - sentToday);

  console.log(`\n=== ${acc.id} (${acc.label || ''}) ===`);
  console.log(`Сегодня уже отправлено: ${sentToday}/${limit}. В очереди: ${pending.length}. Лимит на сегодня: ${budget}.`);

  if (budget === 0 || pending.length === 0) {
    console.log('Пропуск — нечего отправлять.');
    continue;
  }

  // ПРЕДОХРАНИТЕЛЬ от голого IP (для builtin; у dolphin/adspower прокси внутри профиля).
  // Условие идентично openSession: builtin — это ЛЮБОЙ движок кроме dolphin/adspower,
  // иначе опечатка в engine пропустила бы проверку и открыла реальный IP сервера.
  const engine = config.engine || 'builtin';
  if (engine !== 'dolphin' && engine !== 'adspower') {
    const proxy = resolveProxy(config, acc);
    if (!proxy) {
      if (!config.allowNoProxy) {
        console.log('   ! Прокси не задан — запуск ЗАБЛОКИРОВАН (защита аккаунта от голого IP). Задай прокси или allowNoProxy:true.');
        continue;
      }
      console.log('   ⚠ Запуск БЕЗ прокси (allowNoProxy=true) — реальный IP сервера.');
    } else {
      const ip = await checkProxy(proxy);
      if (!ip) {
        console.log('   ! Прокси НЕ отвечает — пропускаю аккаунт, чтобы не светить реальный IP. Запущен ли мост?');
        continue;
      }
      console.log('   прокси OK, внешний IP: ' + ip);
    }
  }

  // Между аккаунтами дёргаем ротацию мобильного IP (у каждого аккаунта — свой свежий IP),
  // но НЕ перед самым первым (его IP и так свежий) и держим IP стабильным внутри сессии.
  if (!firstAccount) await rotateProxyIp(config, console.log);
  firstAccount = false;
  // Случайный сдвиг старта, чтобы аккаунты не били в одну секунду.
  await sleep(Math.floor(Math.random() * 4000));

  let session;
  try {
    session = await openSession(config, acc, { headless: config.headless ?? false });
  } catch (e) {
    console.log('   ! не удалось открыть сессию: ' + e.message);
    continue;
  }
  if (session.proxy) console.log(`   прокси: ${session.proxy.server}${session.proxy.username ? ' (auth)' : ''}`);
  if (session.engine === 'dolphin' || session.engine === 'adspower') {
    console.log(`   движок: ${session.engine} (профиль ${antidetectId(acc)})`);
  }
  const page = session.page;

  try {
    for (const url of pending.slice(0, budget)) {
      process.stdout.write(`-> ${url} ... `);
      // Ловим исключения per-URL, чтобы ошибка одного URL не роняла весь прогон.
      let result;
      try {
        result = await requestIndexing(page, acc.property, url, { min, max });
      } catch (e) {
        console.log('исключение: ' + e.message + ' — пропускаю URL');
        await randomDelay(min, max);
        continue;
      }

      if (result === 'ok') {
        done.add(url);
        sentToday++;
        state[key] = { done: [...done], sent: sentToday };
        await saveState(state);
        console.log('OK');
      } else if (result === 'quota') {
        console.log('ЛИМИТ Google исчерпан — стоп по аккаунту');
        break;
      } else if (result === 'not_logged') {
        console.log('НЕ ЗАЛОГИНЕН — запусти: node src/login.mjs ' + acc.id);
        break;
      } else if (result === 'unknown') {
        // Клик был, но результат не распознан — возможно, уже принято. НЕ переотправляем,
        // но слот квоты, скорее всего, потрачен — учитываем его в дневном счётчике.
        ambiguous.add(url);
        sentToday++;
        state[ambKey] = { urls: [...ambiguous] };
        state[key] = { done: [...done], sent: sentToday };
        await saveState(state);
        console.log('НЕИЗВЕСТНО — возможно, уже принято; помечен на ручную проверку (screenshots/), повтор НЕ будет');
      } else {
        console.log('ошибка (см. screenshots/) — пропускаю');
      }

      await randomDelay(min, max);
    }
  } finally {
    await session.close();
  }
}

console.log('\nГотово.');
process.exit(0);
