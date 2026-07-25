// Каркас панели: боковое меню (ролевое, сгруппированное, сворачиваемое) +
// верхняя панель с названием экрана, темой и профилем.
//
// Что изменилось по сравнению с прежним каркасом и ЗАЧЕМ:
//  - рельс стал светлым и получил иконки: чёрная колонка с мелким текстом
//    читалась как админка 2010-х, а группы различались только словами;
//  - рельс сворачивается в 64px (состояние помнится) — на ноутбуке 13" очередь
//    подтверждений требует ширины;
//  - в шапке появилось название текущего экрана: раньше единственным указателем
//    «где я» была подсветка пункта меню;
//  - у пункта «Подтвердить отправку» висит счётчик писем в очереди: это главная
//    ежедневная работа оператора, ради неё панель и открывают.

import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useAuth } from "../context/auth";
import { navFor, SCREENS, type ScreenDef } from "../lib/screens";
import { Icon, ThemeToggle } from "./ui";
import { getNavCollapsed, setNavCollapsed } from "../lib/theme";

// Иконка на группу меню, а не на каждый пункт: групп семь, пунктов два десятка,
// и «своя картинка на каждый» превратилась бы в шум.
const GROUP_ICON: Record<string, string> = {
  "Лиды": "leads",
  "Обзор": "overview",
  "Инфраструктура": "infra",
  "Комплаенс": "compliance",
  "Администрирование": "admin",
  "Профиль": "profile",
};

function groupIcon(group: string): string {
  return GROUP_ICON[group] || "chains";
}

/** Название текущего экрана для шапки: точное совпадение пути, иначе самый
 *  длинный подходящий префикс (карточка лида, детали кампании). */
function screenTitle(pathname: string): string {
  const exact = SCREENS.find((s) => s.path === pathname);
  if (exact) return exact.title;
  const byPrefix = SCREENS
    .filter((s) => !s.path.includes(":") && s.path !== "/" && pathname.startsWith(s.path))
    .sort((a, b) => b.path.length - a.path.length)[0];
  return byPrefix ? byPrefix.title : "Панель рассылки";
}

export function Layout() {
  const { principal, logout } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [collapsed, setCollapsed] = useState(() => getNavCollapsed());

  // Счётчик очереди подтверждений. Только owner (у менеджера нет такого пункта)
  // и без ретраев: если эндпоинт недоступен, счётчика просто не будет.
  const queue = useQuery({
    queryKey: ["confirm-counts-nav"],
    queryFn: () => api.confirmQueue({ limit: 1 }),
    enabled: principal?.role === "owner",
    refetchInterval: 60_000,
    retry: false,
  });
  const pending = queue.data?.counts?.pending ?? 0;

  if (!principal) return null;

  const items = navFor(principal.role);
  const groups: Record<string, ScreenDef[]> = {};
  for (const s of items) (groups[s.group] ||= []).push(s);

  function toggleRail() {
    const v = !collapsed;
    setCollapsed(v);
    setNavCollapsed(v);
  }

  return (
    <div className={`app${collapsed ? " nav-collapsed" : ""}`}>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">Р</span>
          <span className="brand-text">
            Руспром
            <span className="brand-sub">рассылка</span>
          </span>
        </div>
        <nav aria-label="Разделы панели">
          {Object.entries(groups).map(([group, screens]) => (
            <div key={group} className="nav-group">
              <div className={`nav-group-title ${group.includes("бэклог") ? "backlog-group" : ""}`}>{group}</div>
              {screens.map((s) => (
                <NavLink key={s.path} to={s.path} end={s.path === "/"} title={s.title}
                         className={({ isActive }) => `nav-link ${isActive ? "active" : ""} ${s.live ? "" : "nav-backlog"}`}>
                  <Icon name={groupIcon(group)} className="nav-icon" />
                  <span className="nav-label">{s.title}</span>
                  {!s.live && <span className="nav-tag">бэклог</span>}
                  {s.path === "/confirm" && pending > 0 && (
                    <span className="nav-count" title={`${pending} писем ждут подтверждения`}>{pending}</span>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
      </aside>
      <div className="main">
        <header className="topbar">
          <button className="icon-btn" onClick={toggleRail}
                  title={collapsed ? "Развернуть меню" : "Свернуть меню"}
                  aria-label={collapsed ? "Развернуть меню" : "Свернуть меню"}>
            <Icon name="rail" />
          </button>
          <div className="topbar-title">{screenTitle(loc.pathname)}</div>
          <div className="spacer" />
          <div className="user">
            <ThemeToggle />
            <span className="user-name">{principal.username}</span>
            <span className={`role-tag role-${principal.role}`}>{principal.role === "owner" ? "владелец" : "менеджер"}</span>
            <button className="btn btn-ghost btn-sm" onClick={() => nav("/profile")}>профиль</button>
            <button className="btn btn-ghost btn-sm" title="Выйти"
                    onClick={async () => { await logout(); nav("/login"); }}>
              <Icon name="logout" /> выход
            </button>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
