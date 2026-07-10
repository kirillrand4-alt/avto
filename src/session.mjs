// Единая «сессия браузера» для аккаунта — прячет различие движков:
//   builtin  — наш Chromium с постоянным профилем + прокси + отпечаток;
//   dolphin  — профиль Dolphin{anty} через Local API (прокси/отпечаток внутри Dolphin);
//   adspower — профиль AdsPower через Local API (прокси/отпечаток внутри AdsPower).
// Возвращает { page, engine, proxy?, close() } — дальше логика клика одинаковая.

import { openAccountBrowser, fingerprintFor, resolveProxy } from './lib.mjs';
import { dolphinStart, dolphinStop } from './dolphin.mjs';
import { adspowerStart, adspowerStop } from './adspower.mjs';

// ID профиля антидетекта: новое общее поле profileId, со старым dolphinProfileId как fallback.
export function antidetectId(acc) {
  return acc.profileId || acc.dolphinProfileId || '';
}

export async function openSession(config, acc, { headless = false } = {}) {
  const engine = config.engine || 'builtin';

  if (engine === 'dolphin' || engine === 'adspower') {
    const id = antidetectId(acc);
    if (!id) throw new Error(`У аккаунта ${acc.id} не задан ID профиля антидетекта`);
    const { browser } = engine === 'dolphin'
      ? await dolphinStart(config, id, { headless })
      : await adspowerStart(config, id, { headless });
    // Если получить контекст/страницу не удалось — профиль уже запущен: гасим его,
    // иначе антидетект-профиль и CDP-подключение утекут.
    let context, page;
    try {
      context = browser.contexts()[0] || (await browser.newContext());
      page = context.pages()[0] || (await context.newPage());
    } catch (e) {
      try { await browser.close(); } catch { /* пусто */ }
      if (engine === 'dolphin') await dolphinStop(config, id).catch(() => {});
      else await adspowerStop(config, id).catch(() => {});
      throw e;
    }
    return {
      page,
      engine,
      async close() {
        try { await browser.close(); }
        finally { engine === 'dolphin' ? await dolphinStop(config, id) : await adspowerStop(config, id); }
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
