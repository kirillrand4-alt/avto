import { test, expect, type Page } from "@playwright/test";

// Сквозной флоу против РЕАЛЬНОГО serve-api (сид: owner=kirill, mgr=petrov, 2 лида).

async function login(page: Page, user: string, pass: string) {
  await page.goto("/login");
  await page.getByLabel("Логин").fill(user);
  await page.getByLabel("Пароль").fill(pass);
  await page.getByRole("button", { name: "Войти" }).click();
}

test("owner: логин → дашборд → кампании → backlog честно помечен", async ({ page }) => {
  await login(page, "kirill", "ownerpass1");

  await expect(page.getByRole("heading", { name: "Дашборд" })).toBeVisible();
  await expect(page.locator(".light")).toBeVisible();

  // живой экран (exact — иначе матчит и «Конструктор кампании»)
  await page.getByRole("link", { name: "Кампании", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Кампании" })).toBeVisible();

  // backlog-экран не имитирует данные, а честно сообщает про отсутствующий бэкенд
  // (после 2.2b живыми стали Прогрев/Домены/Аудит — честным бэклогом остались Цепочки/Шаблоны)
  await page.getByRole("link", { name: /Цепочки/ }).click();
  await expect(page.getByText(/бэкенд ещё не построен/)).toBeVisible();
});

test("manager: логин → лента → «Взять» лид (успех)", async ({ page }) => {
  await login(page, "petrov", "mgrpass12");
  await expect(page.getByRole("heading", { name: "Лента лидов" })).toBeVisible();

  const takeButtons = page.getByRole("button", { name: "Взять" });
  await expect(takeButtons.first()).toBeVisible();
  expect(await takeButtons.count()).toBeGreaterThan(0);

  await takeButtons.first().click();
  await expect(page.locator(".toast-success")).toBeVisible();
});

test("конкуренция: второй захват того же лида → конфликт-тост (CAS)", async ({ browser }) => {
  // Два независимых контекста (раздельный localStorage) видят одну ленту.
  const ctxA = await browser.newContext();
  const ctxB = await browser.newContext();
  const a = await ctxA.newPage();
  const b = await ctxB.newPage();
  await login(a, "petrov", "mgrpass12");
  await login(b, "kirill", "ownerpass1");
  await a.goto("/leads");
  await b.goto("/leads");

  const aTake = a.getByRole("button", { name: "Взять" });
  const bTake = b.getByRole("button", { name: "Взять" });
  await expect(aTake.first()).toBeVisible();
  await expect(bTake.first()).toBeVisible();

  // A берёт первый лид (успех). B держит устаревший view (поллинг 15с).
  await aTake.first().click();
  await expect(a.locator(".toast-success")).toBeVisible();

  // B кликает «Взять» на том же (первом) лиде из своего устаревшего списка →
  // сервер отвечает конфликтом (400 not-takeable / 409 CAS) → тост «уже взял другой».
  await bTake.first().click();
  await expect(b.locator(".toast-error")).toBeVisible();
  await expect(b.getByText(/Уже взял другой/)).toBeVisible();

  await ctxA.close();
  await ctxB.close();
});

test("неавторизованный редиректится на /login", async ({ page }) => {
  await page.goto("/leads");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole("heading", { name: "Панель рассылки" })).toBeVisible();
});
