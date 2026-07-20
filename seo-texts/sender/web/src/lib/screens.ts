// Реестр 23 экранов SITE-DESIGN. `live` = есть реальный эндпоинт в sender/api/app.py;
// `backlog` = экран из макета, чей бэкенд ещё не построен (честная заглушка, НЕ фейк).
// Навигация ролевая: owner видит всё, manager — только свою ленту/статистику/профиль.

import type { Role } from "../api/types";

export interface ScreenDef {
  n: number;
  title: string;
  path: string;
  roles: Role[]; // кому виден пункт меню
  live: boolean; // есть реальный эндпоинт
  group: string; // раздел меню
  navHidden?: boolean; // не показывать в меню (детальные роуты)
}

export const SCREENS: ScreenDef[] = [
  // --- Лиды (эпицентр) ---
  { n: 6, title: "Лента лидов", path: "/leads", roles: ["owner", "manager"], live: true, group: "Лиды" },
  { n: 8, title: "Мои лиды", path: "/my-leads", roles: ["owner", "manager"], live: true, group: "Лиды" },
  { n: 9, title: "Моя статистика", path: "/stats", roles: ["owner", "manager"], live: true, group: "Лиды" },
  { n: 7, title: "Карточка лида", path: "/leads/:id", roles: ["owner", "manager"], live: true, group: "Лиды", navHidden: true },

  // --- Обзор (owner) ---
  { n: 2, title: "Дашборд", path: "/", roles: ["owner"], live: true, group: "Обзор" },
  { n: 17, title: "Монитор репутации", path: "/reputation", roles: ["owner"], live: true, group: "Обзор" },
  { n: 3, title: "Кампании", path: "/campaigns", roles: ["owner"], live: true, group: "Обзор" },
  { n: 18, title: "Логи событий", path: "/logs", roles: ["owner"], live: true, group: "Обзор" },

  // --- Инфраструктура (owner) ---
  { n: 15, title: "Ящики и готовность", path: "/mailboxes", roles: ["owner"], live: true, group: "Инфраструктура" },
  { n: 17.1 as unknown as number, title: "Ёмкость пулов", path: "/capacity", roles: ["owner"], live: true, group: "Инфраструктура" },

  // --- Комплаенс (owner) ---
  { n: 19, title: "Suppression", path: "/suppression", roles: ["owner"], live: true, group: "Комплаенс" },

  // --- Профиль (все) ---
  { n: 22, title: "Профиль", path: "/profile", roles: ["owner", "manager"], live: true, group: "Профиль" },

  // --- BACKLOG: экраны макета без эндпоинта (нужен бэкенд Фазы 2.1+) ---
  { n: 4, title: "Конструктор кампании", path: "/campaigns/new", roles: ["owner"], live: false, group: "Кампании (бэклог)" },
  { n: 5, title: "Детали кампании", path: "/campaigns/:id", roles: ["owner"], live: false, group: "Кампании (бэклог)", navHidden: true },
  { n: 10, title: "Цепочки", path: "/sequences", roles: ["owner"], live: false, group: "Цепочки (бэклог)" },
  { n: 12, title: "Шаблоны", path: "/templates", roles: ["owner"], live: false, group: "Цепочки (бэклог)" },
  { n: 14, title: "Домены (DNS)", path: "/domains", roles: ["owner"], live: false, group: "Инфраструктура (бэклог)" },
  { n: 16, title: "Прогрев", path: "/warmup", roles: ["owner"], live: false, group: "Инфраструктура (бэклог)" },
  { n: 20, title: "Комплаенс-центр", path: "/compliance", roles: ["owner"], live: false, group: "Комплаенс (бэклог)" },
  { n: 21, title: "Настройки", path: "/settings", roles: ["owner"], live: false, group: "Настройки (бэклог)" },
  { n: 23, title: "Аудит действий", path: "/audit", roles: ["owner"], live: false, group: "Настройки (бэклог)" },
];

export function navFor(role: Role): ScreenDef[] {
  return SCREENS.filter((s) => !s.navHidden && s.roles.includes(role));
}

/** Причина, почему экран пока заглушка — для честной подписи. */
export const BACKLOG_ENDPOINTS: Record<string, string> = {
  "/campaigns/new": "POST /campaigns, POST /campaigns/:id/steps (не построены)",
  "/campaigns/:id": "GET /campaigns/:id + воронка (не построены)",
  "/sequences": "GET /sequences (не построен)",
  "/templates": "GET /templates (не построен)",
  "/domains": "GET /domains/:d + DnsHealth-эндпоинт (dns.py есть, роут — нет)",
  "/warmup": "GET /warmup (не построен)",
  "/compliance": "GET /compliance, GET /subject/:email (не построены)",
  "/settings": "GET/POST /users, /settings (не построены)",
  "/audit": "GET /audit (audit_log в БД есть, роут — нет)",
};
