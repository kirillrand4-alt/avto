// Каркас панели: боковое меню (ролевое, сгруппированное) + верхняя панель с
// профилем/выходом. Backlog-разделы визуально помечены.

import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/auth";
import { navFor, type ScreenDef } from "../lib/screens";

export function Layout() {
  const { principal, logout } = useAuth();
  const nav = useNavigate();
  if (!principal) return null;

  const items = navFor(principal.role);
  const groups: Record<string, ScreenDef[]> = {};
  for (const s of items) (groups[s.group] ||= []).push(s);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">Руспром · рассылка</div>
        <nav>
          {Object.entries(groups).map(([group, screens]) => (
            <div key={group} className="nav-group">
              <div className={`nav-group-title ${group.includes("бэклог") ? "backlog-group" : ""}`}>{group}</div>
              {screens.map((s) => (
                <NavLink key={s.path} to={s.path} end={s.path === "/"}
                         className={({ isActive }) => `nav-link ${isActive ? "active" : ""} ${s.live ? "" : "nav-backlog"}`}>
                  {s.title}{!s.live && <span className="nav-tag">бэклог</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="spacer" />
          <div className="user">
            <span className="muted">{principal.username}</span>
            <span className={`role-tag role-${principal.role}`}>{principal.role === "owner" ? "владелец" : "менеджер"}</span>
            <button className="btn btn-ghost" onClick={() => nav("/profile")}>профиль</button>
            <button className="btn btn-ghost" onClick={async () => { await logout(); nav("/login"); }}>выход</button>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
