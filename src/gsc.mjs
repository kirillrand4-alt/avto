import { randomDelay, SCREENSHOTS_DIR } from './lib.mjs';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';

// Строит прямую ссылку на инструмент проверки URL в Search Console.
// property: 'sc-domain:example.com' (domain property) или 'https://www.example.com/' (url-prefix)
export function inspectUrl(property, url) {
  const params = new URLSearchParams({ resource_id: property, id: url });
  return `https://search.google.com/search-console/inspect?${params.toString()}`;
}

// Тексты кнопок/статусов на русском и английском — UI GSC локализован.
const RE_REQUEST = /(Запросить индекс|Request indexing|Запросить инд)/i;
const RE_SUCCESS = /(добавлен в очередь|очередь на сканирование|priority crawl|added to a priority|Indexing requested|Запрос на индексирование отправлен)/i;
const RE_QUOTA = /(превышена квота|превышен.*лимит|Quota exceeded|exceeded your daily|попробуйте завтра|try again tomorrow)/i;

async function screenshot(page, name) {
  await mkdir(SCREENSHOTS_DIR, { recursive: true }).catch(() => {});
  const file = path.join(SCREENSHOTS_DIR, `${name}-${Date.now()}.png`);
  await page.screenshot({ path: file, fullPage: false }).catch(() => {});
  return file;
}

// Отправляет один URL на индексацию. Возвращает:
//   'ok'        — успешно поставлен в очередь
//   'quota'     — упёрлись в дневной лимит Google (дальше по этому аккаунту нет смысла)
//   'not_logged'— сессия слетела, нужен повторный login
//   'error'     — прочая ошибка (сделан скриншот)
export async function requestIndexing(page, property, url, { min, max }) {
  await page.goto(inspectUrl(property, url), { waitUntil: 'domcontentloaded' });

  // Если редиректнуло на страницу логина — сессия истекла.
  if (/accounts\.google\.com/.test(page.url())) {
    return 'not_logged';
  }

  // Ждём, пока инспекция отработает и появится кнопка запроса индексации.
  const requestBtn = page.getByText(RE_REQUEST).first();
  try {
    await requestBtn.waitFor({ state: 'visible', timeout: 60000 });
  } catch {
    const shot = await screenshot(page, 'no-request-button');
    console.warn(`   ! кнопка "Запросить индексирование" не найдена. Скриншот: ${shot}`);
    return 'error';
  }

  await randomDelay(min, max);
  await requestBtn.click();

  // Google тестирует "живой" URL — это может занять до минуты. Затем диалог с результатом.
  const deadline = Date.now() + 90000;
  while (Date.now() < deadline) {
    const body = await page.textContent('body').catch(() => '');
    if (RE_QUOTA.test(body)) return 'quota';
    if (RE_SUCCESS.test(body)) {
      // Закрываем диалог, если есть кнопка "Готово"/"OK"/крестик.
      await page.getByRole('button', { name: /(Готово|OK|Закрыть|Got it|Close|Done)/i })
        .first().click({ timeout: 3000 }).catch(() => {});
      return 'ok';
    }
    await page.waitForTimeout(2000);
  }

  const shot = await screenshot(page, 'timeout');
  console.warn(`   ! не дождались подтверждения. Скриншот: ${shot}`);
  return 'error';
}
