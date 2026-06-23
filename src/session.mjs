// Единая «сессия браузера» для аккаунта — прячет различие движков:
//   builtin — наш Chromium с постоянным профилем + прокси + отпечаток;
//   dolphin — профиль Dolphin{anty} через Local API (прокси/отпечаток внутри Dolphin).
// Возвращает { page, engine, proxy?, close() } — дальше логика клика одинаковая.

import { openAccountBrowser, fingerprintFor, resolveProxy } from './lib.mjs';
import { dolphinStart, dolphinStop } from './dolphin.mjs';

export async function openSession(config, acc, { headless = false } = {}) {
  const engine = config.engine || 'builtin';

  if (engine === 'dolphin') {
    if (!acc.dolphinProfileId) {
      throw new Error(`У аккаунта ${acc.id} не задан Dolphin Profile ID`);
    }
    const { browser } = await dolphinStart(config, acc.dolphinProfileId);
    const context = browser.contexts()[0] || (await browser.newContext());
    const page = context.pages()[0] || (await context.newPage());
    return {
      page,
      engine,
      async close() {
        try { await browser.close(); } finally { await dolphinStop(config, acc.dolphinProfileId); }
      },
    };
  }

  // builtin
  const proxy = resolveProxy(config, acc);
  const context = await openAccountBrowser(acc.id, {
    headless,
    proxy,
    fingerprint: fingerprintFor(acc.id, config),
  });
  const page = context.pages()[0] || (await context.newPage());
  return { page, engine, proxy, async close() { await context.close(); } };
}
