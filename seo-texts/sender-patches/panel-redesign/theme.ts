// Тема панели: светлая / тёмная / как в системе.
//
// ЗАЧЕМ вообще тема: оператор сидит в очереди подтверждений часами, в том числе
// вечером. Тёмная тема тут не украшение, а гигиена зрения.
//
// ЗАЧЕМ ставить data-theme даже для режима «системная»: CSS тогда нужен ровно в
// двух вариантах (:root и :root[data-theme="dark"]), а не в трёх с медиазапросами
// внутри каждого правила. Выбор пользователя хранится отдельно от применённого
// значения: prefer = "system", а на <html> висит уже разрешённое light/dark.

export type ThemePref = "light" | "dark" | "system";
export type ThemeApplied = "light" | "dark";

const KEY = "sender.theme";

/** Что просил пользователь (или «системная», если не выбирал). */
export function getThemePref(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    /* приватный режим / отключённое хранилище: молча живём на системной */
  }
  return "system";
}

/** Что говорит система (в тестовой среде matchMedia может отсутствовать). */
export function systemTheme(): ThemeApplied {
  try {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  } catch {
    return "light";
  }
}

export function resolveTheme(pref: ThemePref): ThemeApplied {
  return pref === "system" ? systemTheme() : pref;
}

/** Применить тему к документу. Возвращает то, что реально применилось. */
export function applyTheme(pref: ThemePref): ThemeApplied {
  const applied = resolveTheme(pref);
  const root = document.documentElement;
  root.setAttribute("data-theme", applied);
  root.setAttribute("data-theme-pref", pref);
  return applied;
}

/** Сохранить выбор и применить его. */
export function setThemePref(pref: ThemePref): ThemeApplied {
  try {
    localStorage.setItem(KEY, pref);
  } catch {
    /* не смогли сохранить: тема доживёт до перезагрузки, это не повод падать */
  }
  return applyTheme(pref);
}

/** Порядок в кнопке-переключателе: светлая -> тёмная -> системная. */
export function nextThemePref(pref: ThemePref): ThemePref {
  return pref === "light" ? "dark" : pref === "dark" ? "system" : "light";
}

export const THEME_LABELS: Record<ThemePref, string> = {
  light: "светлая тема",
  dark: "тёмная тема",
  system: "как в системе",
};

/** Разово применить сохранённый выбор при старте SPA. */
export function initTheme(): ThemeApplied {
  return applyTheme(getThemePref());
}

// Сайдбар сворачивается в узкий рельс. Живёт рядом с темой: это тоже
// «внешний вид, который панель обязана помнить между заходами».
const NAV_KEY = "sender.nav.collapsed";

export function getNavCollapsed(): boolean {
  try {
    return localStorage.getItem(NAV_KEY) === "1";
  } catch {
    return false;
  }
}

export function setNavCollapsed(v: boolean): void {
  try {
    localStorage.setItem(NAV_KEY, v ? "1" : "0");
  } catch {
    /* см. выше: отсутствие хранилища не ломает интерфейс */
  }
}
