import { test, expect, type Page } from "@playwright/test";

// Флоу владельца по оживлённым экранам 2.2b: создать кампанию → добавить шаг →
// запустить; команда (создать менеджера); домены-сводка; аудит фиксирует действия.

async function loginOwner(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Логин").fill("kirill");
  await page.getByLabel("Пароль").fill("ownerpass1");
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page.getByRole("heading", { name: "Дашборд" })).toBeVisible();
}

test("owner: создать кампанию → шаг → запустить → аудит", async ({ page }) => {
  await loginOwner(page);

  await page.getByRole("link", { name: "Новая кампания" }).click();
  await page.getByPlaceholder("Прогрев ритейл").fill("E2E кампания");
  await page.getByRole("button", { name: "Создать" }).click();

  // редирект на детали
  await expect(page.getByRole("heading", { name: "E2E кампания" })).toBeVisible();

  // добавить шаг
  await page.getByPlaceholder(/Тема письма/).fill("Тема {company_name}");
  await page.getByPlaceholder(/Текст письма/).fill("Здравствуйте, {company_name}!");
  await page.getByRole("button", { name: "Добавить шаг" }).click();
  // может копиться несколько тостов (создание+шаг) — целимся по тексту
  await expect(page.locator(".toast-success").getByText("Шаг добавлен")).toBeVisible();

  // запустить
  await page.getByRole("button", { name: "Запустить" }).click();
  await expect(page.locator(".badge").getByText("active")).toBeVisible();

  // аудит зафиксировал
  await page.getByRole("link", { name: "Аудит действий" }).click();
  await expect(page.getByText("campaign.create")).toBeVisible();
  await expect(page.getByText("campaign.add_step")).toBeVisible();
});

test("owner: команда — создать менеджера, увидеть в таблице", async ({ page }) => {
  await loginOwner(page);
  await page.getByRole("link", { name: "Настройки и команда" }).click();
  await expect(page.getByRole("heading", { name: "Настройки" })).toBeVisible();

  const uniq = "mgr" + Date.now().toString().slice(-6);
  await page.getByPlaceholder("логин").fill(uniq);
  await page.getByPlaceholder("пароль (8+)").fill("password123");
  await page.getByRole("button", { name: "Добавить" }).click();
  await expect(page.locator(".toast-success")).toBeVisible();
  await expect(page.getByRole("cell", { name: uniq })).toBeVisible();
});

test("owner: домены — сводка видна", async ({ page }) => {
  await loginOwner(page);
  await page.getByRole("link", { name: "Домены (DNS)" }).click();
  await expect(page.getByRole("heading", { name: "Домены отправки" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Проверить DNS" }).first()).toBeVisible();
});
