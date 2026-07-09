// Человекоподобное поведение мыши/клавиатуры для Playwright.
// Настоящие движения курсора по кубической кривой с асимметричным профилем скорости
// (ранний пик, как у человека — закон Фиттса), проскоком (overshoot) и микрокоррекциями
// у цели, лог-нормальные задержки (длинный правый хвост, без жёстких обрезов),
// «чтение» страницы, человеческий набор текста. Снижает поведенческий детект.

const rnd = (min, max) => min + Math.random() * (max - min);
const rndInt = (min, max) => Math.floor(rnd(min, max + 1));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Стандартная нормаль (Box–Muller).
function gauss() {
  let u = 0, v = 0;
  while (u === 0) u = Math.random();
  while (v === 0) v = Math.random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}
// Лог-нормальная задержка (мс): медиана = median, правый хвост задаёт sigma.
// softMax — мягкий потолок лишь для крайне редких выбросов (без жёсткого обреза по краям).
function lognormal(median, sigma = 0.4, softMax = median * 6) {
  return Math.min(Math.exp(Math.log(median) + sigma * gauss()), softMax);
}

// Асимметричный профиль скорости: строим неравномерное расписание t по интегралу
// скорости v(u)=u*(1-u)^1.5 (пик ~u=0.4) — быстрый разгон, длинное торможение.
function buildEase(steps) {
  const v = []; let sum = 0;
  for (let i = 1; i <= steps; i++) { const u = i / steps; const vi = u * Math.pow(1 - u, 1.5); v.push(vi); sum += vi; }
  const t = [0]; let acc = 0;
  for (let i = 0; i < steps; i++) { acc += v[i]; t.push(acc / sum); }
  return t; // t[0]=0 ... t[steps]=1, монотонно, неравномерно
}

// Текущая позиция курсора храним на самой page (Playwright её не отдаёт).
// Стартовая точка — ближе к нижнему краю (как будто курсор «вошёл» снизу), а не из центра.
function pos(page) {
  if (!page.__mousePos) {
    const vp = (page.viewportSize && page.viewportSize()) || { width: 1366, height: 768 };
    page.__mousePos = { x: rnd(vp.width * 0.2, vp.width * 0.8), y: rnd(vp.height * 0.75, vp.height - 4) };
  }
  return page.__mousePos;
}

// Прокрутка колесом сериями дискретных «тиков», а не одним крупным delta.
async function wheelTicks(page, total) {
  const ticks = rndInt(3, 6);
  const per = total / ticks;
  for (let i = 0; i < ticks; i++) {
    await page.mouse.wheel(0, per + rnd(-per * 0.3, per * 0.3));
    await sleep(lognormal(90, 0.5));
  }
}

// Плавное движение к (tx, ty): кубическая Безье + overshoot + микрокоррекции у цели.
export async function moveMouse(page, tx, ty) {
  const start = pos(page);
  const dist = Math.hypot(tx - start.x, ty - start.y);
  const steps = Math.max(12, Math.min(48, Math.round(dist / 10)));
  // иногда «промахиваемся» за цель — основной бросок целится чуть дальше
  const willOvershoot = Math.random() < 0.6 && dist > 40;
  const dx = dist ? (tx - start.x) / dist : 0;
  const dy = dist ? (ty - start.y) / dist : 0;
  const os = willOvershoot ? rnd(3, 12) : 0;
  const aimx = tx + dx * os, aimy = ty + dy * os;
  // две контрольные точки — дуга с возможным изломом, а не идеальная парабола
  const c1x = start.x + (aimx - start.x) * 0.33 + rnd(-0.2, 0.2) * dist;
  const c1y = start.y + (aimy - start.y) * 0.33 + rnd(-0.2, 0.2) * dist;
  const c2x = start.x + (aimx - start.x) * 0.66 + rnd(-0.2, 0.2) * dist;
  const c2y = start.y + (aimy - start.y) * 0.66 + rnd(-0.2, 0.2) * dist;
  const ease = buildEase(steps);
  for (let i = 1; i <= steps; i++) {
    const t = ease[i], mt = 1 - t;
    let x = mt * mt * mt * start.x + 3 * mt * mt * t * c1x + 3 * mt * t * t * c2x + t * t * t * aimx;
    let y = mt * mt * mt * start.y + 3 * mt * mt * t * c1y + 3 * mt * t * t * c2y + t * t * t * aimy;
    const jitter = Math.sin(Math.PI * (i / steps)) * 1.6; // дрожание сильнее в середине пути
    x += rnd(-jitter, jitter);
    y += rnd(-jitter, jitter);
    await page.mouse.move(x, y);
    await sleep(Math.random() < 0.08 ? lognormal(80, 0.5) : lognormal(6, 0.5));
  }
  // корректирующие микродвижения к реальной цели; посадка с остаточной ошибкой ±1-3px
  let curx = aimx, cury = aimy;
  const corrections = willOvershoot ? rndInt(1, 2) : (Math.random() < 0.3 ? 1 : 0);
  for (let k = 0; k < corrections; k++) {
    const tight = (k === corrections - 1) ? 1 : 2;
    curx = tx + rnd(-2, 2) * tight;
    cury = ty + rnd(-2, 2) * tight;
    await sleep(lognormal(70, 0.4));
    await page.mouse.move(curx, cury);
  }
  if (corrections === 0) { curx = tx + rnd(-2, 2); cury = ty + rnd(-2, 2); await page.mouse.move(curx, cury); }
  page.__mousePos = { x: curx, y: cury }; // не идеальная точка, а с микроошибкой
}

// Клик по элементу как человек: прокрутить в вид, навести (по кривой) в случайную точку
// внутри, микропауза, нажать/отпустить с задержкой.
export async function humanClick(page, locator) {
  // Прокрутка в зону видимости — иначе boundingBox даст координаты за вьюпортом и клик промахнётся.
  await locator.scrollIntoViewIfNeeded({ timeout: 5000 }).catch(() => {});
  const box = await locator.boundingBox().catch(() => null);
  if (!box) { await locator.click({ timeout: 5000 }).catch(() => {}); return; }
  const tx = box.x + box.width * rnd(0.3, 0.7);
  const ty = box.y + box.height * rnd(0.3, 0.7);
  await moveMouse(page, tx, ty);
  await sleep(lognormal(120, 0.45));
  await page.mouse.down();
  await sleep(lognormal(75, 0.35));
  await page.mouse.up();
}

// «Чтение» страницы: пара движений мыши и лёгкий скролл туда-обратно.
export async function idleBrowse(page) {
  const vp = page.viewportSize() || { width: 1366, height: 768 };
  const rounds = rndInt(1, 3);
  for (let i = 0; i < rounds; i++) {
    await moveMouse(page, rnd(80, vp.width - 80), rnd(80, vp.height - 80));
    await sleep(lognormal(280, 0.5));
    if (Math.random() < 0.7) {
      await wheelTicks(page, rnd(60, 320));
      await sleep(lognormal(380, 0.5));
    }
  }
  if (Math.random() < 0.5) {
    await wheelTicks(page, -rnd(40, 200)); // немного назад, как человек
    await sleep(lognormal(250, 0.45));
  }
}

// Набор текста по-человечески (лог-нормальные паузы между символами).
export async function humanType(page, locator, text) {
  await humanClick(page, locator);
  for (const ch of text) {
    await page.keyboard.type(ch);
    await sleep(lognormal(105, 0.5));
  }
}

// Пауза «на подумать» с лог-нормальным распределением вокруг медианы диапазона.
export const humanPause = (min = 400, max = 1500) =>
  sleep(lognormal((min + max) / 2, 0.4, max * 2));
