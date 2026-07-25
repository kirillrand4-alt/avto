// Переиспользуемые UI-примитивы панели: иконки, состояния (загрузка/пусто/
// ошибка), бейджи статусов, светофор, флаги причин, постраничность, плитки.
//
// Правила этого файла:
//  1) внешних библиотек нет — панель работает во внутренней сети, иконки
//     инлайновые SVG, шрифты системные;
//  2) состояние НИКОГДА не передаётся одним цветом: рядом всегда значок и
//     слово (дальтонизм, печать, ч/б экран удалённого доступа);
//  3) пропсы старых компонентов не меняются — экраны, которые редизайн не
//     трогал, обязаны продолжать работать.

import { useState, type ReactNode, type SVGProps } from "react";
import { ApiError } from "../api/client";
import { BACKLOG_ENDPOINTS } from "../lib/screens";
import {
  getThemePref, nextThemePref, setThemePref, THEME_LABELS, type ThemePref,
} from "../lib/theme";

/* ======================= иконки ======================= */

// Набор ровно под нужды панели: меню, состояния, действия. Все 16x16, обводкой
// currentColor — цвет наследуется от текста, отдельных «цветных» иконок нет.
const PATHS: Record<string, ReactNode> = {
  leads: <><circle cx="6.5" cy="5.5" r="2.5" /><path d="M2 13.5a4.5 4.5 0 0 1 9 0" /><path d="M11 3.4a2.5 2.5 0 0 1 0 4.2" /><path d="M12.2 9.6a4 4 0 0 1 1.8 3.3" /></>,
  overview: <><path d="M2.5 12a5.5 5.5 0 1 1 11 0" /><path d="M8 12l2.8-3.2" /></>,
  infra: <><rect x="2.5" y="3" width="11" height="4.5" rx="1.2" /><rect x="2.5" y="8.5" width="11" height="4.5" rx="1.2" /><path d="M5 5.2h.01M5 10.7h.01" /></>,
  compliance: <><path d="M8 2.2l5 1.9v3.8c0 3-2 5.2-5 6-3-.8-5-3-5-6V4.1z" /><path d="M5.9 8.1l1.5 1.5 2.7-3" /></>,
  admin: <><path d="M3 5h9M4 11h9" /><circle cx="6" cy="5" r="1.7" /><circle cx="11" cy="11" r="1.7" /></>,
  profile: <><circle cx="8" cy="5.5" r="2.5" /><path d="M3.5 13.5a4.5 4.5 0 0 1 9 0" /></>,
  chains: <><path d="M6.6 9.4a3 3 0 0 0 4.2 0l1.5-1.5a3 3 0 0 0-4.2-4.2l-.8.8" /><path d="M9.4 6.6a3 3 0 0 0-4.2 0L3.7 8.1a3 3 0 0 0 4.2 4.2l.8-.8" /></>,
  mail: <><rect x="2" y="3.5" width="12" height="9" rx="1.5" /><path d="M2.6 5l5.4 4 5.4-4" /></>,
  stop: <><circle cx="8" cy="8" r="6" /><path d="M4.2 11.8L11.8 4.2" /></>,
  warn: <><path d="M8 2.6l6 11H2z" /><path d="M8 6.6v3.2M8 11.7h.01" /></>,
  info: <><circle cx="8" cy="8" r="6" /><path d="M8 7.4v3.4M8 5.2h.01" /></>,
  ok: <><circle cx="8" cy="8" r="6" /><path d="M5.4 8.2l1.9 1.9 3.3-3.8" /></>,
  inbox: <><path d="M3.4 3.5h9.2l1.4 5.6v3.4H2V9.1z" /><path d="M2 9.4h3.4l.9 1.8h3.4l.9-1.8H14" /></>,
  search: <><circle cx="7" cy="7" r="4.2" /><path d="M10.2 10.2l3.3 3.3" /></>,
  sun: <><circle cx="8" cy="8" r="3" /><path d="M8 1.2v1.6M8 13.2v1.6M1.2 8h1.6M13.2 8h1.6M3.3 3.3l1.1 1.1M11.6 11.6l1.1 1.1M12.7 3.3l-1.1 1.1M4.4 11.6l-1.1 1.1" /></>,
  moon: <><path d="M13.2 9.6A5.6 5.6 0 0 1 6.4 2.8a5.6 5.6 0 1 0 6.8 6.8z" /></>,
  monitor: <><rect x="2" y="3" width="12" height="8" rx="1.4" /><path d="M6 13.4h4" /></>,
  left: <><path d="M10 3.6L5.6 8l4.4 4.4" /></>,
  right: <><path d="M6 3.6L10.4 8 6 12.4" /></>,
  rail: <><rect x="2" y="3" width="12" height="10" rx="1.6" /><path d="M6.4 3v10" /></>,
  logout: <><path d="M6.2 3.4H3.6v9.2h2.6" /><path d="M9.4 5.6L11.8 8l-2.4 2.4" /><path d="M11.8 8H6.4" /></>,
};

export type IconName = keyof typeof PATHS | string;

export function Icon({ name, className, ...rest }: { name: IconName } & SVGProps<SVGSVGElement>) {
  const body = PATHS[name];
  if (!body) return null;
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor"
         strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
         className={className} aria-hidden="true" focusable="false" {...rest}>
      {body}
    </svg>
  );
}

/* ======================= состояния ======================= */

/** Скелет строки: показываем каркас будущего контента, а не пустоту. */
export function Skeleton({ w = "100%", h = 12 }: { w?: string | number; h?: number }) {
  return <span className="skeleton" style={{ width: w, height: h }} />;
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="card skeleton-card" aria-busy="true" aria-live="polite">
      {Array.from({ length: rows }).map((_, r) => (
        <div className="skeleton-row" key={r}>
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} w={c === 0 ? "22%" : `${Math.max(12, 30 - c * 4)}%`} />
          ))}
        </div>
      ))}
    </div>
  );
}

/** Совместимость: старые экраны зовут <Spinner /> вместо скелета. */
export function Spinner({ label = "Загрузка…" }: { label?: string }) {
  return (
    <div className="center muted" role="status" aria-live="polite">
      <span className="spinner-inline" /> {label}
    </div>
  );
}

export function Alert({ kind = "info", title, children, actions }: {
  kind?: "danger" | "warn" | "ok" | "info";
  title?: string; children?: ReactNode; actions?: ReactNode;
}) {
  const icon = kind === "danger" ? "stop" : kind === "warn" ? "warn" : kind === "ok" ? "ok" : "info";
  return (
    <div className={`alert alert-${kind}`} role={kind === "danger" ? "alert" : "status"}>
      <Icon name={icon} className="alert-icon" />
      <div className="alert-body">
        {title && <div className="alert-title">{title}</div>}
        {children}
      </div>
      {actions && <div className="alert-actions">{actions}</div>}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  let msg = "Ошибка";
  let title = "Не удалось загрузить данные";
  if (error instanceof ApiError) {
    if (error.status === 403) { title = "Нет доступа"; msg = "Раздел доступен только роли owner."; }
    else if (error.status === 401) { title = "Сессия истекла"; msg = "Войдите заново."; }
    else { msg = error.detail; }
  } else if (error instanceof Error) {
    msg = error.message;
  }
  return (
    <Alert kind="danger" title={title}
           actions={onRetry && <button className="btn btn-sm" onClick={onRetry}>Повторить</button>}>
      {msg}
    </Alert>
  );
}

/** Пусто: не только «нет данных», но и что с этим делать. */
export function Empty({ hint, title = "Нет данных", icon = "inbox", action }: {
  hint?: string; title?: string; icon?: IconName; action?: ReactNode;
}) {
  return (
    <div className="empty">
      <Icon name={icon} className="empty-icon" width={40} height={40} />
      <div className="empty-title">{title}</div>
      {hint && <div className="muted">{hint}</div>}
      {action && <div className="empty-actions">{action}</div>}
    </div>
  );
}

/* ======================= данные ======================= */

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

/** Бейдж направления бизнеса: КЦ (компрессоры) или Meyer (рентген/сепараторы). */
export function DivisionBadge({ division, fallback }: { division?: string | null; fallback?: string }) {
  const d = (division || "").toLowerCase();
  if (d === "meyer") return <span className="badge badge-div-meyer">Meyer</span>;
  if (d === "kc" || d === "кц") return <span className="badge badge-div-kc">КЦ</span>;
  return <span className="badge">{fallback || division || "направление не определено"}</span>;
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
      <Icon name={ready ? "ok" : "warn"} width={12} height={12} />
      {ready ? "готов к бою" : human.join(", ") || "не готов"}
    </span>
  );
}

/** Полоса заполнения: лимиты ящиков, загрузка пулов, части скоринга. */
export function Meter({ value, max, tone }: { value: number; max: number; tone?: "ok" | "warn" | "danger" }) {
  const p = max > 0 ? Math.round((100 * Math.min(Math.max(value, 0), max)) / max) : 0;
  const auto = tone ?? (p >= 95 ? "danger" : p >= 80 ? "warn" : undefined);
  return (
    <span className="meter" role="img" aria-label={`${value} из ${max}`} title={`${value} / ${max}`}>
      <span className={`meter-fill${auto ? ` ${auto}` : ""}`} style={{ width: `${p}%` }} />
    </span>
  );
}

/** Плитка метрики для дашборда и сводок. */
export function StatTile({ label, value, hint, tone }: {
  label: string; value: ReactNode; hint?: ReactNode; tone?: "ok" | "warn" | "danger";
}) {
  return (
    <div className={`stat${tone ? ` stat-${tone}` : ""}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint != null && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

/* ======================= флаги причин ======================= */

export type FlagInput = { code?: string; label: string; severity?: string };

/** Один флаг: значок + слово-категория + текст. Цвет — третий по счёту сигнал,
 *  а не единственный (требование доступности к экрану подтверждений). */
export function Flag({ level, label, code }: { level: "stop" | "warn"; label: string; code?: string }) {
  const stop = level === "stop";
  return (
    <div className={`flag flag-${stop ? "stop" : "warn"}`}
         role={stop ? "alert" : "status"} data-code={code}>
      <Icon name={stop ? "stop" : "warn"} className="flag-icon" />
      <span className="flag-kind">{stop ? "стоп" : "внимание"}</span>
      <span className="flag-text">{label}</span>
    </div>
  );
}

/** Разбор списка стоп-флагов панели: severity=yellow — предупреждение,
 *  всё остальное (включая пустое) — жёсткий стоп. */
export function FlagList({ flags, note }: { flags: FlagInput[]; note?: string }) {
  if (!flags || flags.length === 0) return null;
  const stops = flags.filter((f) => (f.severity || "red") !== "yellow");
  const warns = flags.filter((f) => f.severity === "yellow");
  return (
    <div className="flags" data-testid="stop-flags">
      {stops.map((f, i) => <Flag key={`s${i}`} level="stop" label={f.label} code={f.code} />)}
      {warns.map((f, i) => <Flag key={`w${i}`} level="warn" label={f.label} code={f.code} />)}
      {note && <div className="flags-note">{note}</div>}
    </div>
  );
}

/* ======================= навигация по длинным спискам ======================= */

/** Постраничность. Виртуализация не нужна: страница держится в 25 строк,
 *  а DOM в 25 строк браузер отрисует мгновенно на любой длине очереди. */
export function Pager({ offset, shown, total, onPrev, onNext, unit = "записей" }: {
  offset: number; shown: number; total?: number;
  onPrev: () => void; onNext: () => void; unit?: string;
}) {
  const from = shown === 0 ? 0 : offset + 1;
  const to = offset + shown;
  const canPrev = offset > 0;
  // Следующая страница есть, если пришла полная страница (сервер отдаёт срез
  // без общего числа) или если общее число известно и больше показанного.
  const canNext = total != null ? to < total : shown > 0;
  return (
    <div className="pager">
      <button className="btn btn-sm" disabled={!canPrev} onClick={onPrev} aria-label="Предыдущая страница">
        <Icon name="left" /> назад
      </button>
      <span className="grow">
        {from}–{to}{total != null ? ` из ${total}` : ""} {unit}
      </span>
      <button className="btn btn-sm" disabled={!canNext} onClick={onNext} aria-label="Следующая страница">
        вперёд <Icon name="right" />
      </button>
    </div>
  );
}

/* ======================= прочее ======================= */

/** Клавиша-хоткей в подписи кнопки. */
export function Kbd({ children }: { children: ReactNode }) {
  return <span className="kbd">{children}</span>;
}

/** Переключатель темы: светлая -> тёмная -> системная. */
export function ThemeToggle() {
  const [pref, setPref] = useState<ThemePref>(() => getThemePref());
  const icon = pref === "light" ? "sun" : pref === "dark" ? "moon" : "monitor";
  return (
    <button className="icon-btn" title={`Оформление: ${THEME_LABELS[pref]}`}
            aria-label={`Оформление: ${THEME_LABELS[pref]}. Переключить`}
            onClick={() => { const n = nextThemePref(pref); setThemePref(n); setPref(n); }}>
      <Icon name={icon} />
    </button>
  );
}

/** Честная заглушка экрана из макета без бэкенда. */
export function BacklogStub({ title, path }: { title: string; path: string }) {
  const ep = BACKLOG_ENDPOINTS[path] || "эндпоинт не построен";
  return (
    <div className="backlog">
      <h1>{title}</h1>
      <div className="backlog-badge">
        <Icon name="warn" width={12} height={12} />
        Экран из макета SITE-DESIGN, бэкенд ещё не построен
      </div>
      <p className="muted">Требуется: <code>{ep}</code></p>
      <p className="muted">
        Экран заложен в навигацию для полноты маршрутизации, но не имитирует данные.
        Появится после расширения API (Фаза 2.1+). Живые экраны — в остальных разделах меню.
      </p>
    </div>
  );
}

export function Card({ title, children, actions, note, className }: {
  title?: string; children: ReactNode; actions?: ReactNode; note?: ReactNode; className?: string;
}) {
  return (
    <section className={`card${className ? ` ${className}` : ""}`}>
      {(title || actions) && (
        <div className="card-head">
          {title && <h2 className="card-title">{title}</h2>}
          {actions && <div className="card-actions">{actions}</div>}
        </div>
      )}
      {note && <p className="card-note">{note}</p>}
      {children}
    </section>
  );
}
