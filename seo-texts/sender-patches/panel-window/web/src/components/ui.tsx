// Мелкие переиспользуемые UI-примитивы: бейджи статусов, светофор, спиннер,
// ошибка, пустое состояние, заглушка бэклога.

import { type ReactNode } from "react";
import { ApiError } from "../api/client";
import { BACKLOG_ENDPOINTS } from "../lib/screens";

export function Spinner() {
  return <div className="center muted">Загрузка…</div>;
}

export function ErrorBox({ error }: { error: unknown }) {
  let msg = "Ошибка";
  if (error instanceof ApiError) {
    msg = error.status === 403 ? "Нет доступа (нужна роль owner)"
      : error.status === 401 ? "Сессия истекла"
      : error.detail;
  } else if (error instanceof Error) {
    msg = error.message;
  }
  return <div className="errorbox">⚠ {msg}</div>;
}

export function Empty({ hint }: { hint?: string }) {
  return (
    <div className="empty">
      <div className="empty-title">Нет данных</div>
      {hint && <div className="muted">{hint}</div>}
    </div>
  );
}

/** Светофор репутации: цвет = худшая метрика. SITE-DESIGN §2 экран 2/17. */
export function TrafficLight({ complaintRate, bounceRate }: { complaintRate: number; bounceRate: number }) {
  // пороги: complaint <0.08 зел / 0.08–0.1 жёлт / >0.1 крас; bounce <2.5/2.5–3/>3
  const c = complaintRate > 0.1 ? 2 : complaintRate >= 0.08 ? 1 : 0;
  const b = bounceRate > 3 ? 2 : bounceRate >= 2.5 ? 1 : 0;
  const level = Math.max(c, b);
  const cls = level === 2 ? "red" : level === 1 ? "yellow" : "green";
  const label = level === 2 ? "Красный" : level === 1 ? "Жёлтый" : "Зелёный";
  return (
    <span className={`light light-${cls}`} title={`complaint ${complaintRate.toFixed(3)}% / bounce ${bounceRate.toFixed(2)}%`}>
      <span className="dot" /> {label}
    </span>
  );
}

const LEAD_STATUS: Record<string, string> = {
  new: "новый", taken: "взят", called: "позвонил", qualified: "квал",
  not_qualified: "не квал", in_bitrix: "в Bitrix",
};

export function StatusBadge({ status, kind = "lead" }: { status: string; kind?: "lead" | "campaign" }) {
  const label = kind === "lead" ? (LEAD_STATUS[status] || status) : status;
  return <span className={`badge badge-${status}`}>{label}</span>;
}

// Человекочитаемые причины «почему ящик не готов» (было: англо-коды).
const READY_REASON_LABELS: Record<string, string> = {
  outside_window: "вне окна авто-отправки",
  paused: "на паузе",
  gate_tripped: "сработал гейт репутации",
  quota_exhausted: "исчерпан дневной лимит",
};

export function readyReasonLabel(code: string): string {
  return READY_REASON_LABELS[code] || code;
}

export function ReadyBadge({ ready, reasons }: { ready: boolean; reasons: string[] }) {
  const human = (reasons || []).map(readyReasonLabel);
  const note =
    !ready && reasons?.includes("outside_window")
      ? "Ограничивает только авто-отправку; ручное подтверждение из очереди уходит всегда."
      : undefined;
  return (
    <span className={`badge ${ready ? "badge-qualified" : "badge-not_qualified"}`}
          title={[human.join(", "), note].filter(Boolean).join(" · ") || undefined}>
      {ready ? "готов к бою" : human.join(", ") || "не готов"}
    </span>
  );
}

/** Честная заглушка экрана из макета без бэкенда. */
export function BacklogStub({ title, path }: { title: string; path: string }) {
  const ep = BACKLOG_ENDPOINTS[path] || "эндпоинт не построен";
  return (
    <div className="backlog">
      <h1>{title}</h1>
      <div className="backlog-badge">Экран из макета SITE-DESIGN — бэкенд ещё не построен</div>
      <p className="muted">Требуется: <code>{ep}</code></p>
      <p className="muted">
        Экран заложен в навигацию для полноты маршрутизации, но не имитирует данные.
        Появится после расширения API (Фаза 2.1+). Живые экраны — в остальных разделах меню.
      </p>
    </div>
  );
}

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className="card">
      {title && <h2 className="card-title">{title}</h2>}
      {children}
    </section>
  );
}
