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
  { n: 6.5 as unknown as number, title: "Почта", path: "/mail", roles: ["owner", "manager"], live: true, group: "Лиды" },
  { n: 7, title: "Карточка лида", path: "/leads/:id", roles: ["owner", "manager"], live: true, group: "Лиды", navHidden: true },

  // --- Обзор (owner) ---
  { n: 2, title: "Дашборд", path: "/", roles: ["owner"], live: true, group: "Обзор" },
  { n: 17, title: "Монитор репутации", path: "/reputation", roles: ["owner"], live: true, group: "Обзор" },
  { n: 3, title: "Кампании", path: "/campaigns", roles: ["owner"], live: true, group: "Обзор" },
  { n: 18, title: "Логи событий", path: "/logs", roles: ["owner"], live: true, group: "Обзор" },

  // --- Инфраструктура (owner) ---
  { n: 15, title: "Ящики и готовность", path: "/mailboxes", roles: ["owner"], live: true, group: "Инфраструктура" },
  { n: 17.1 as unknown as number, title: "Ёмкость пулов", path: "/capacity", roles: ["owner"], live: true, group: "Инфраструктура" },

  // --- Кампании (owner) ---
  { n: 4, title: "Новая кампания", path: "/campaigns/new", roles: ["owner"], live: true, group: "Обзор" },
  { n: 5, title: "Детали кампании", path: "/campaigns/:id", roles: ["owner"], live: true, group: "Обзор", navHidden: true },

  // --- Инфраструктура (owner) ---
  { n: 13, title: "База получателей", path: "/recipients", roles: ["owner"], live: true, group: "Инфраструктура" },
  { n: 14, title: "Домены (DNS)", path: "/domains", roles: ["owner"], live: true, group: "Инфраструктура" },
  { n: 14.1 as unknown as number, title: "Добавить домен", path: "/domains/new", roles: ["owner"], live: true, group: "Инфраструктура" },
  { n: 16, title: "Прогрев", path: "/warmup", roles: ["owner"], live: true, group: "Инфраструктура" },

  // --- Комплаенс (owner) ---
  { n: 24, title: "Подтвердить отправку", path: "/confirm", roles: ["owner"], live: true, group: "Комплаенс" },
  { n: 19, title: "Suppression", path: "/suppression", roles: ["owner"], live: true, group: "Комплаенс" },
  { n: 20, title: "Комплаенс-центр", path: "/compliance", roles: ["owner"], live: true, group: "Комплаенс" },

  // --- Администрирование (owner) ---
  { n: 21, title: "Настройки и команда", path: "/settings", roles: ["owner"], live: true, group: "Администрирование" },
  { n: 23, title: "Аудит действий", path: "/audit", roles: ["owner"], live: true, group: "Администрирование" },

  // --- Профиль (все) ---
  { n: 22, title: "Профиль", path: "/profile", roles: ["owner", "manager"], live: true, group: "Профиль" },

  // --- BACKLOG: экраны без ОТДЕЛЬНОЙ сущности/эндпоинта (цепочки=шаги кампании) ---
  { n: 10, title: "Цепочки", path: "/sequences", roles: ["owner"], live: false, group: "Цепочки (бэклог)" },
  { n: 12, title: "Шаблоны", path: "/templates", roles: ["owner"], live: false, group: "Цепочки (бэклог)" },
];

export function navFor(role: Role): ScreenDef[] {
  return SCREENS.filter((s) => !s.navHidden && s.roles.includes(role));
}

/** Причина, почему экран пока заглушка — для честной подписи. */
export const BACKLOG_ENDPOINTS: Record<string, string> = {
  "/sequences": "отдельной сущности «цепочка» в движке нет — это шаги кампании (см. Детали кампании); нужен /sequences CRUD с реордером шагов",
  "/templates": "отдельной сущности «шаблон» нет — subject/body живут в шаге; нужен /templates CRUD",
};
