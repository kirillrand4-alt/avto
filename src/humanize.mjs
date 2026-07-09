// Человекоподобное поведение мыши/клавиатуры для Playwright.
// Настоящие движения курсора по кривой Безье с дрожанием и ускорением, клики со
// смещением от центра, «чтение» страницы, набор текста с паузами. Снижает роботность.

const rnd = (min, max) => min + Math.random() * (max - min);
const rndInt = (min, max) => Math.floor(rnd(min, max + 1));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const easeInOut = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);

// Текущая позиция курсора храним на самой page (Playwright её не отдаёт).
function pos(page) {
  if (!page.__mousePos) page.__mousePos = { x: rnd(60, 300), y: rnd(60, 300) };
  return page.__mousePos;
}

// Плавное движение к (tx, ty) по квадратичной кривой Безье со случайными паузами.
export async function moveMouse(page, tx, ty) {
  const start = pos(page);
  const dist = Math.hypot(tx - start.x, ty - start.y);
  const steps = Math.max(12, Math.min(48, Math.round(dist / 10)));
  // контрольная точка — уводит траекторию в сторону (дуга, а не прямая)
  const cx = (start.x + tx) / 2 + rnd(-0.25, 0.25) * dist;
  const cy = (start.y + ty) / 2 + rnd(-0.25, 0.25) * dist;
  for (let i = 1; i <= steps; i++) {
    const t = easeInOut(i / steps);
    const mt = 1 - t;
    let x = mt * mt * start.x + 2 * mt * t * cx + t * t * tx;
    let y = mt * mt * start.y + 2 * mt * t * cy + t * t * ty;
    // микродрожание руки (сильнее в середине пути, слабее у цели)
    const jitter = Math.sin(Math.PI * (i / steps)) * 1.6;
    x += rnd(-jitter, jitter);
    y += rnd(-jitter, jitter);
    await page.mouse.move(x, y);
    // иногда человек на миг замирает
    await sleep(Math.random() < 0.08 ? rnd(40, 160) : rnd(3, 16));
  }
  await page.mouse.move(tx, ty);
  page.__mousePos = { x: tx, y: ty };
}

// Клик по элементу как человек: навести (по кривой) в случайную точку внутри,
// микропауза, нажать/отпустить с задержкой.
export async function humanClick(page, locator) {
  // Сначала прокручиваем элемент в зону видимости — иначе boundingBox даст
  // координаты за пределами вьюпорта и клик мышью промахнётся.
  await locator.scrollIntoViewIfNeeded({ timeout: 5000 }).catch(() => {});
  const box = await locator.boundingBox().catch(() => null);
  if (!box) { await locator.click({ timeout: 5000 }).catch(() => {}); return; }
  const tx = box.x + box.width * rnd(0.3, 0.7);
  const ty = box.y + box.height * rnd(0.3, 0.7);
  await moveMouse(page, tx, ty);
  await sleep(rnd(60, 220));
  await page.mouse.down();
  await sleep(rnd(45, 130));
  await page.mouse.up();
}

// «Чтение» страницы: пара движений мыши и лёгкий скролл туда-обратно.
export async function idleBrowse(page) {
  const vp = page.viewportSize() || { width: 1366, height: 768 };
  const rounds = rndInt(1, 3);
  for (let i = 0; i < rounds; i++) {
    await moveMouse(page, rnd(80, vp.width - 80), rnd(80, vp.height - 80));
    await sleep(rnd(120, 500));
    if (Math.random() < 0.7) {
      await page.mouse.wheel(0, rnd(60, 320));
      await sleep(rnd(200, 700));
    }
  }
  if (Math.random() < 0.5) {
    await page.mouse.wheel(0, -rnd(40, 200)); // немного назад, как человек
    await sleep(rnd(150, 400));
  }
}

// Набор текста по-человечески (разные паузы между символами).
export async function humanType(page, locator, text) {
  await humanClick(page, locator);
  for (const ch of text) {
    await page.keyboard.type(ch);
    await sleep(rnd(60, 200));
  }
}

export const humanPause = (min = 400, max = 1500) => sleep(rnd(min, max));
