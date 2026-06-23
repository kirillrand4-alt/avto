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

import { loadConfig, openAccountBrowser } from './lib.mjs';

const only = process.argv[2];

const config = await loadConfig();
const accounts = only ? config.accounts.filter((a) => a.id === only) : config.accounts;

if (accounts.length === 0) {
  console.error('Аккаунты не найдены в config.json' + (only ? ` (id=${only})` : ''));
  process.exit(1);
}

for (const acc of accounts) {
  console.log(`\n=== Логин: ${acc.id} (${acc.label || ''}) ===`);
  console.log('1) Войди в нужный Google-аккаунт');
  console.log('2) Открой Search Console и убедись, что видишь свойство:', acc.property);
  console.log('3) Закрой окно браузера, чтобы перейти к следующему аккаунту.');

  const context = await openAccountBrowser(acc.id, { headless: false });
  const page = context.pages()[0] || (await context.newPage());
  await page.goto('https://search.google.com/search-console', { waitUntil: 'domcontentloaded' });

  // Ждём, пока пользователь сам закроет браузер.
  await new Promise((resolve) => context.on('close', resolve));
  console.log(`Профиль для ${acc.id} сохранён.`);
}

console.log('\nГотово. Теперь можно запускать: npm run run');
process.exit(0);
