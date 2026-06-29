// Первичный логин в аккаунты.
//
// Запускается РУКАМИ один раз на каждый аккаунт. Открывает браузер с постоянным
// профилем, ты логинишься в Google (вводишь пароль, проходишь 2FA/капчу сам),
// заходишь в Search Console — и закрываешь. Сессия останется в profiles/<id>,
// дальше run.mjs будет использовать её без повторного входа.
//
// Использование:
//   node src/login.mjs            -> по очереди все аккаунты из config.json
//   node src/login.mjs acc1       -> только конкретный аккаунт

import { loadConfig, openAccountBrowser, fingerprintFor, resolveProxy, checkProxy, rotateProxyIp } from './lib.mjs';
import { dolphinStart, dolphinStop } from './dolphin.mjs';
import readline from 'node:readline';

const only = process.argv[2];

const config = await loadConfig();
const engine = config.engine || 'builtin';
const accounts = only ? config.accounts.filter((a) => a.id === only) : config.accounts;

if (accounts.length === 0) {
  console.error('Аккаунты не найдены в config.json' + (only ? ` (id=${only})` : ''));
  process.exit(1);
}

function waitEnter(prompt) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => rl.question(prompt, () => { rl.close(); resolve(); }));
}

for (const acc of accounts) {
  console.log(`\n=== Логин: ${acc.id} (${acc.label || ''}) ===`);
  console.log('1) Войди в нужный Google-аккаунт');
  console.log('2) Открой Search Console и убедись, что видишь свойство:', acc.property);

  if (engine === 'dolphin') {
    // Dolphin сам поднимает окно с прокси/отпечатком профиля.
    if (!acc.dolphinProfileId) {
      console.warn(`   ! у ${acc.id} не задан Dolphin Profile ID — пропуск. Укажи его в панели.`);
      continue;
    }
    console.log(`3) Окно профиля Dolphin ${acc.dolphinProfileId} откроется само. Залогинься в нём.`);
    const { browser } = await dolphinStart(config, acc.dolphinProfileId);
    const context = browser.contexts()[0] || (await browser.newContext());
    const page = context.pages()[0] || (await context.newPage());
    await page.goto('https://search.google.com/search-console', { waitUntil: 'domcontentloaded' }).catch(() => {});
    await waitEnter('   Когда вошёл и видишь Search Console — нажми Enter, чтобы закрыть профиль...');
    await browser.close().catch(() => {});
    await dolphinStop(config, acc.dolphinProfileId);
    console.log(`Профиль Dolphin для ${acc.id} готов.`);
    continue;
  }

  // builtin
  console.log('3) Закрой окно браузера, чтобы перейти к следующему аккаунту.');
  const proxy = resolveProxy(config, acc);

  // ПРЕДОХРАНИТЕЛЬ: не логинить аккаунт без рабочего прокси (главная причина банов).
  if (!proxy) {
    if (!config.allowNoProxy) {
      console.warn(`   ! Прокси не задан — вход в ${acc.id} ЗАБЛОКИРОВАН (защита от голого IP). Задай прокси или allowNoProxy:true.`);
      continue;
    }
    console.warn('   ⚠ Вход БЕЗ прокси (allowNoProxy=true) — реальный IP сервера.');
  } else {
    const ip = await checkProxy(proxy);
    if (!ip) {
      console.warn('   ! Прокси НЕ отвечает — пропускаю вход, чтобы не светить реальный IP. Запущен ли мост?');
      continue;
    }
    console.log('   прокси OK, внешний IP:', ip);
    // ротация IP перед каждым входом — чтобы разные аккаунты не логинились с одного IP
    await rotateProxyIp(config, console.log);
  }
  if (proxy) console.log('   через прокси:', proxy.server + (proxy.username ? ' (auth)' : ''));
  const context = await openAccountBrowser(acc.id, {
    headless: false,
    proxy,
    fingerprint: fingerprintFor(acc.id, config),
  });
  const page = context.pages()[0] || (await context.newPage());
  page.setDefaultNavigationTimeout(90000);
  // Навигация нежёсткая: через медленный мобильный прокси домен может грузиться долго.
  // Если не успело — окно всё равно остаётся открытым, залогинишься вручную.
  await page.goto('https://search.google.com/search-console', { waitUntil: 'commit', timeout: 90000 })
    .catch((e) => console.log(`   (страница грузится медленно: ${e.message}). Окно открыто — войди и при необходимости сам открой Search Console.`));
  await new Promise((resolve) => context.on('close', resolve));
  console.log(`Профиль для ${acc.id} сохранён.`);
}

console.log('\nГотово. Теперь можно запускать: npm run run');
process.exit(0);
