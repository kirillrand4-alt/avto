// Живые экраны-таблицы над реальными эндпоинтами: кампании, логи, репутация,
// suppression, ящики, ёмкость, моя статистика, профиль.

import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { useAuth } from "../context/auth";
import { useToast } from "../components/Toast";
import { Pager, Spinner, ErrorBox, Empty, Card, StatusBadge, ReadyBadge } from "../components/ui";
import { fmtDate, pct, maskEmail } from "../lib/format";
import type { Campaign, QuotaDay, SentMessage } from "../api/types";

const WEEKDAY_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

function quotaDayLabel(d: QuotaDay): string {
  const p = d.date.split("-");
  return `${WEEKDAY_SHORT[(d.weekday || 1) - 1]} ${p[2]}.${p[1]}`;
}

/** Карточка «Дневная квота генерации»: расписание дата → сколько писем,
 *  факт за день по ai_letter_log и ручной запуск догенерации на сегодня.
 *  Расписание, а не одно число: владелец задаёт темп «3 сегодня, 3 завтра,
 *  5 послезавтра». */
function AiQuotaCard({ campaigns }: { campaigns: Campaign[] }) {
  const { principal } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const isOwner = principal?.role === "owner";
  const [cid, setCid] = useState<number>(campaigns[0]?.id ?? 0);
  const [draft, setDraft] = useState<Record<string, number>>({});
  const q = useQuery({
    queryKey: ["ai-quota", cid],
    queryFn: () => api.aiQuota(cid),
    enabled: cid > 0,
    // Пока прогон идёт — счётчики подтягиваем сами: генерация одного письма
    // это несколько LLM-раундов, оператор не должен жать F5.
    refetchInterval: (query) => (query.state.data?.run?.running ? 5000 : false),
  });
  const save = useMutation({
    mutationFn: () => api.setAiQuota(cid, draft),
    onSuccess: () => {
      toast("success", "Расписание квоты сохранено");
      setDraft({});
      qc.invalidateQueries({ queryKey: ["ai-quota", cid] });
    },
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : String(e)),
  });
  const run = useMutation({
    mutationFn: () => api.runAiQuota(cid),
    onSuccess: () => {
      toast("success", "Генерация запущена — письма пойдут в очередь подтверждений");
      qc.invalidateQueries({ queryKey: ["ai-quota", cid] });
    },
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : String(e)),
  });
  if (campaigns.length === 0) return null;
  const data = q.data;
  const todayLeft = data
    ? (data.days.find((d) => d.date === data.today)?.remaining ?? 0)
    : 0;
  const st = data?.run;
  let runNote = "";
  if (st?.running) runNote = "прогон идёт, счётчики обновляются сами";
  else if (st?.error) runNote = `последний прогон упал: ${st.error}`;
  else if (st?.result) {
    const r = st.result;
    runNote = r.reason
      ? `последний прогон (${r.date}): ${r.reason}`
      : `последний прогон (${r.date}): в очередь ${r.generated}, брак ${r.rejected}`;
  }
  if (st?.stale) runNote += " — прогон оборвался (служба перезапускалась)";
  return (
    <Card title="Дневная квота генерации">
      <p className="muted" style={{ marginTop: 0 }}>
        Сколько писем генерировать в день: «3 сегодня, 3 завтра, 5 послезавтра».
        Квоту съедают все попытки, включая брак — это расход провайдерского API.
        Повторный запуск в тот же день догенерирует только недостающее, письма
        уходят в очередь подтверждений, а не в отправку.
      </p>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
        <label>Кампания{" "}
          <select value={cid} onChange={(e) => { setCid(Number(e.target.value)); setDraft({}); }}>
            {campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <span className="muted">
          без письма в сегменте: {data ? data.candidates_left : "—"}
        </span>
      </div>
      {q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} /> : !data ? null : (
        <>
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>День</th><th>Квота</th><th>Сгенерировано</th><th>Брак</th><th>Осталось</th></tr></thead>
              <tbody>{data.days.map((d) => {
                const val = draft[d.date] ?? d.quota;
                const isToday = d.date === data.today;
                return (
                  <tr key={d.date} style={isToday ? { fontWeight: 600 } : undefined}>
                    <td>{quotaDayLabel(d)}{isToday ? " (сегодня)" : ""}</td>
                    <td>
                      <input type="number" min={0} max={200} value={val} style={{ width: 70 }}
                             disabled={!isOwner || save.isPending}
                             onChange={(e) => setDraft({
                               ...draft,
                               [d.date]: Math.max(0, Math.min(200, Number(e.target.value) || 0)),
                             })} />
                    </td>
                    <td>{d.generated}</td>
                    <td>{d.rejected || "—"}</td>
                    <td>{d.remaining}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 8 }}>
            {isOwner && (
              <button className="btn btn-primary"
                      disabled={!Object.keys(draft).length || save.isPending}
                      onClick={() => save.mutate()}>Сохранить расписание</button>
            )}
            {isOwner && (
              <button className="btn"
                      disabled={run.isPending || !!st?.running || todayLeft === 0}
                      onClick={() => run.mutate()}>
                {st?.running ? "Генерация идёт…" : `Сгенерировать сейчас (${todayLeft})`}
              </button>
            )}
            <span className="muted">{runNote}</span>
          </div>
        </>
      )}
    </Card>
  );
}

// ---- Экран 3: Кампании (список) ----
export function Campaigns() {
  const q = useQuery({ queryKey: ["campaigns"], queryFn: () => api.campaigns() });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  const rows = q.data!.campaigns;
  return (
    <div>
      <div className="page-head"><h1>Кампании</h1><div className="muted">{rows.length} шт.</div></div>
      <p className="muted small">Создание/редактирование кампаний — раздел «Кампании (бэклог)»: нужны POST-эндпоинты.</p>
      <AiQuotaCard campaigns={rows} />
      {rows.length === 0 ? <Empty hint="Создайте кампанию через CLI: python -m sender campaign-create" /> : (
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>#</th><th>Название</th><th>Статус</th><th>Юрлицо</th><th>Создана</th></tr></thead>
            <tbody>{rows.map((c) => (
              <tr key={c.id}><td>{c.id}</td><td>{c.name}</td><td><StatusBadge status={c.status} kind="campaign" /></td>
                <td>{c.legal_entity}</td><td>{fmtDate(c.created_at)}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---- Экран 18: Логи событий ----
export function Logs() {
  const [type, setType] = useState("");
  // пейджер: владелец вливает всю базу — события листаются, а не обрезаются на 200
  const [offset, setOffset] = useState(0);
  const PAGE = 200;
  const q = useQuery({ queryKey: ["events", type, offset], queryFn: () => api.events({ event_type: type || undefined, limit: PAGE, offset }) });
  const rows = q.data?.events ?? [];
  return (
    <div>
      <div className="page-head"><h1>Логи событий</h1></div>
      <div className="filterbar">
        <label>Тип
          <select value={type} onChange={(e) => { setType(e.target.value); setOffset(0); }}>
            {["", "sent", "delivered", "bounce", "complaint", "reply", "unsubscribe", "suppress"].map((t) =>
              <option key={t} value={t}>{t || "все"}</option>)}
          </select>
        </label>
      </div>
      {q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} /> :
        rows.length === 0 ? <Empty /> : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>#</th><th>Тип</th><th>Кампания</th><th>Провайдер</th><th>Ящик</th><th>Время</th></tr></thead>
              <tbody>{rows.map((e) => (
                <tr key={e.id}><td>{e.id}</td><td><StatusBadge status={e.event_type} kind="campaign" /></td>
                  <td>{e.campaign_id ?? "—"}</td><td>{e.provider ?? "—"}</td><td>{e.mailbox_id ?? "—"}</td>
                  <td>{fmtDate(e.event_ts)}</td></tr>
              ))}</tbody>
            </table>
          </div>
        )}
      <Pager offset={offset} shown={rows.length} unit="событий"
        onPrev={() => setOffset(Math.max(0, offset - PAGE))}
        onNext={() => setOffset(offset + PAGE)} />
    </div>
  );
}

// ---- Экран 17: Монитор репутации ----
export function Reputation() {
  const gates = useQuery({ queryKey: ["gates"], queryFn: () => api.gatesActive(), refetchInterval: 30_000 });
  const series = useQuery({ queryKey: ["rates"], queryFn: () => api.rates({ scope: "global", target: "*", days: 7 }) });
  const trips = gates.data?.trips ?? [];
  const pts = series.data?.series ?? [];
  return (
    <div>
      <div className="page-head"><h1>Монитор репутации</h1></div>
      <Card title="Сработавшие гейты">
        {gates.isLoading ? <Spinner /> : trips.length === 0 ? <p className="muted">Нет активных срабатываний.</p> : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Скоуп</th><th>Цель</th><th>Метрика</th><th>Значение</th><th>Порог</th></tr></thead>
              <tbody>{trips.map((t, i) => (
                <tr key={i} className="row-hot"><td>{t.scope}</td><td>{t.target}</td><td>{t.metric}</td>
                  <td className="danger">{pct(t.value)}</td><td>{pct(t.threshold)}</td></tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Card>
      <Card title="Динамика 7 дней (global)">
        {series.isLoading ? <Spinner /> : pts.length === 0 ? <Empty /> : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>День</th><th>Отпр.</th><th>Bounce</th><th>Жалобы</th><th>Ответы</th><th>BR%</th><th>CR%</th></tr></thead>
              <tbody>{pts.map((p, i) => (
                <tr key={i}><td>{p.target}</td><td>{p.sent}</td><td>{p.bounce}</td><td>{p.complaint}</td>
                  <td>{p.reply}</td><td>{pct(p.bounce_rate)}</td><td>{pct(p.complaint_rate)}</td></tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

// ---- Экран 19: Suppression ----
export function Suppression() {
  const { principal } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [scope, setScope] = useState("");
  const [offset, setOffset] = useState(0);
  const PAGE = 200;
  const q = useQuery({ queryKey: ["suppression", scope, offset], queryFn: () => api.suppression({ scope: scope || undefined, limit: PAGE, offset }) });
  const rm = useMutation({
    mutationFn: (sid: number) => api.removeSuppression(sid, "operator removal"),
    onSuccess: () => { toast("success", "Удалено (записано в аудит)"); qc.invalidateQueries({ queryKey: ["suppression"] }); },
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : "Ошибка"),
  });
  const rows = q.data?.suppression ?? [];
  // Массовая загрузка ИНН (владелец 06.08): вставить список компаний, где уже
  // идёт сделка, — рассыльщик их не трогает. Парсит сервер (строки/запятые/
  // колонка Excel), повторная загрузка того же списка ничего не дублирует.
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkText, setBulkText] = useState("");
  const [bulkReason, setBulkReason] = useState("deal_in_progress");
  const bulk = useMutation({
    mutationFn: () => api.suppressionBulkInn(bulkText, bulkReason),
    onSuccess: (d) => {
      toast("success", `ИНН в запрет: добавлено ${d.added}, уже было ${d.existed}`
        + (d.invalid.length ? ` · не разобрано ${d.invalid.length}: ${d.invalid.slice(0, 3).join(", ")}…` : ""));
      setBulkText("");
      qc.invalidateQueries({ queryKey: ["suppression"] });
    },
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : "Ошибка загрузки"),
  });
  return (
    <div>
      <div className="page-head"><h1>Suppression (ФЗ-152)</h1></div>
      <div className="filterbar">
        <label>Скоуп
          <select value={scope} onChange={(e) => { setScope(e.target.value); setOffset(0); }}>
            {["", "email", "domain", "inn"].map((s) => <option key={s} value={s}>{s || "все"}</option>)}
          </select>
        </label>
        {principal?.role === "owner" && (
          <button className="btn" onClick={() => setBulkOpen(!bulkOpen)}>
            {bulkOpen ? "скрыть загрузку" : "Загрузить список ИНН"}
          </button>
        )}
      </div>
      {bulkOpen && principal?.role === "owner" && (
        <div className="card" style={{ margin: "8px 0", padding: 12 }}>
          <div className="muted small" style={{ marginBottom: 6 }}>
            Вставьте ИНН (10 или 12 цифр) — по одному в строке, через запятую
            или колонкой из Excel. Эти компании рассыльщик трогать не будет.
          </div>
          <textarea rows={6} style={{ width: "100%", fontFamily: "monospace" }}
                    value={bulkText} placeholder={"7701234567\n5027000000\n…"}
                    onChange={(e) => setBulkText(e.target.value)} />
          <div className="row" style={{ marginTop: 6 }}>
            <label className="muted">причина{" "}
              <select value={bulkReason} onChange={(e) => setBulkReason(e.target.value)}>
                <option value="deal_in_progress">идёт сделка</option>
                <option value="competitor">конкурент</option>
                <option value="manual">ручной запрет</option>
              </select>
            </label>
            <button className="btn" disabled={bulk.isPending || !bulkText.trim()}
                    onClick={() => bulk.mutate()}>
              Загрузить в запрет
            </button>
          </div>
        </div>
      )}
      {q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} /> :
        rows.length === 0 ? <Empty /> : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>#</th><th>Скоуп</th><th>Значение</th><th>Причина</th><th>Добавлено</th><th></th></tr></thead>
              <tbody>{rows.map((s) => (
                <tr key={s.id}><td>{s.id}</td><td>{s.scope}</td>
                  <td>{s.scope === "email" ? maskEmail(s.value) : s.value}</td>
                  <td>{s.reason}</td><td>{fmtDate(s.created_at)}</td>
                  <td>{principal?.role === "owner" && (
                    <button className="btn btn-ghost danger" disabled={rm.isPending}
                            onClick={() => { if (confirm(`Удалить из suppression? Разбан жалобщика опасен.`)) rm.mutate(s.id); }}>
                      удалить
                    </button>
                  )}</td></tr>
              ))}</tbody>
            </table>
          </div>
        )}
      <Pager offset={offset} shown={rows.length} unit="записей"
        onPrev={() => setOffset(Math.max(0, offset - PAGE))}
        onNext={() => setOffset(offset + PAGE)} />
    </div>
  );
}

// ---- Окно авто-отправки (настройка владельцем) ----
const DAY_LABELS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const TZ_OPTIONS = [
  ["Europe/Kaliningrad", "Калининград (МСК-1)"],
  ["Europe/Moscow", "Москва (МСК)"],
  ["Europe/Samara", "Самара (МСК+1)"],
  ["Asia/Yekaterinburg", "Екатеринбург (МСК+2)"],
  ["Asia/Omsk", "Омск (МСК+3)"],
  ["Asia/Novosibirsk", "Новосибирск/Барнаул (МСК+4)"],
  ["Asia/Krasnoyarsk", "Красноярск (МСК+4)"],
  ["Asia/Irkutsk", "Иркутск (МСК+5)"],
  ["Asia/Yakutsk", "Якутск (МСК+6)"],
  ["Asia/Vladivostok", "Владивосток (МСК+7)"],
];

function OutOfBaseToggleCard() {
  const { principal } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["out-of-base"], queryFn: () => api.allowOutOfBase() });
  const save = useMutation({
    mutationFn: (allow: boolean) => api.setAllowOutOfBase(allow),
    onSuccess: () => {
      toast("success", "Настройка сохранена");
      qc.invalidateQueries({ queryKey: ["out-of-base"] });
    },
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : String(e)),
  });
  if (q.isLoading || !q.data) return null;
  const isOwner = principal?.role === "owner";
  const on = q.data.allow_out_of_base;
  return (
    <Card title="Отправка по адресам вне базы">
      <p className="muted" style={{ marginTop: 0 }}>
        По умолчанию письма адресатам, чей ИНН НЕ в базе обзвона, блокируются на
        подтверждении (направление не определено). Включите, если осознанно шлёте
        по новым/внешним контактам.
      </p>
      <label style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
        <input type="checkbox" disabled={!isOwner || save.isPending}
               checked={on} onChange={(e) => save.mutate(e.target.checked)} />
        <b>{on ? "ВКЛ — слать вне базы разрешено" : "ВЫКЛ — только по базе (безопасно)"}</b>
      </label>
    </Card>
  );
}

function SendingWindowCard() {
  const { principal } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["sending-window"], queryFn: () => api.sendingWindow() });
  const [draft, setDraft] = useState<null | {
    days: number[]; start: string; end: string; tz: string; by_recipient_tz?: boolean;
  }>(null);
  const save = useMutation({
    mutationFn: () => api.setSendingWindow(draft!),
    onSuccess: () => {
      toast("success", "Окно авто-отправки сохранено");
      setDraft(null);
      qc.invalidateQueries({ queryKey: ["sending-window"] });
      qc.invalidateQueries({ queryKey: ["readiness"] });
    },
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : String(e)),
  });
  if (q.isLoading || !q.data) return null;
  // tz сервер отдаёт всегда (обе ветки /sending-window его проставляют), но
  // подстраховка автора сохранена — просто записана так, чтобы не затирать
  // пришедшее значение литералом (было `{ tz: ..., ...window }` — TS2783).
  const cur = draft ?? { ...q.data.window, tz: q.data.window.tz || "Europe/Moscow" };
  const isOwner = principal?.role === "owner";
  const toggleDay = (d: number) => {
    const days = cur.days.includes(d) ? cur.days.filter((x) => x !== d) : [...cur.days, d];
    setDraft({ ...cur, days });
  };
  return (
    <Card title="Окно авто-отправки">
      <p className="muted" style={{ marginTop: 0 }}>
        Автоматика шлёт только в эти дни/часы (по выбранному поясу). Ручное
        подтверждение из очереди работает всегда — окно его не ограничивает.
      </p>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
        {DAY_LABELS.map((label, i) => (
          <label key={label} style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
            <input type="checkbox" disabled={!isOwner}
                   checked={cur.days.includes(i + 1)} onChange={() => toggleDay(i + 1)} />
            {label}
          </label>
        ))}
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        с <input type="time" value={cur.start} disabled={!isOwner}
                 onChange={(e) => setDraft({ ...cur, start: e.target.value })} />
        до <input type="time" value={cur.end} disabled={!isOwner}
                  onChange={(e) => setDraft({ ...cur, end: e.target.value })} />
        <select value={cur.tz || "Europe/Moscow"} disabled={!isOwner}
                onChange={(e) => setDraft({ ...cur, tz: e.target.value })}>
          {TZ_OPTIONS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </select>
        {isOwner && draft && (
          <button className="btn btn-primary" disabled={save.isPending || !cur.days.length}
                  onClick={() => save.mutate()}>Сохранить</button>
        )}
        <span className="muted">
          {q.data.source === "override" ? "задано из панели" : "из конфига (не переопределено)"}
        </span>
      </div>
      {/* «По времени получателя» (владелец 06.08). Пояс берётся из региона
          РЕГИСТРАЦИИ компании: где зарегистрирована — то и считаем её временем,
          даже если у неё есть офис в Москве. */}
      <div style={{ marginTop: 10 }}>
        <label style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
          <input type="checkbox" disabled={!isOwner}
                 checked={Boolean(cur.by_recipient_tz)}
                 onChange={(e) => setDraft({ ...cur, by_recipient_tz: e.target.checked })} />
          <b>по времени получателя</b>
        </label>
        <div className="muted small" style={{ marginTop: 4 }}>
          {cur.by_recipient_tz
            ? "часы считаются в поясе региона регистрации получателя: 09:00 в Иркутске — это 09:00 по Иркутску"
            : "часы считаются в одном поясе, выбранном выше, для всех получателей"}
        </div>
      </div>
    </Card>
  );
}

// ---- Экран 15: Ящики и готовность ----
/** Ручной потолок дневной отправки. Ручки были и потерялись при синхронизации
 *  репозитория с боем; заодно проводка: раньше настройка сохранялась, а
 *  отправка её не читала — тумблер ничего не ограничивал. Теперь читает
 *  Sender._daily_limit, и только ВНИЗ: выше рампы поднять нельзя. */
function SendLimitsCard() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["send-limits"], queryFn: () => api.sendLimits() });
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [all, setAll] = useState<string>("");
  const save = useMutation({
    mutationFn: () => api.setSendLimits({
      all: all.trim() === "" ? null : Number(all),
      per_mailbox: Object.fromEntries(Object.entries(draft).map(
        ([k, v]) => [k, v.trim() === "" ? null : Number(v)])),
    }),
    onSuccess: () => {
      toast("success", "Лимиты сохранены");
      setDraft({});
      qc.invalidateQueries({ queryKey: ["send-limits"] });
      qc.invalidateQueries({ queryKey: ["readiness"] });
    },
    onError: (e) => toast("error", `Лимиты: ${(e as Error).message}`),
  });
  if (q.isLoading) return <Card title="Дневной лимит отправки"><Spinner /></Card>;
  if (q.error) return <Card title="Дневной лимит отправки"><ErrorBox error={q.error} /></Card>;
  const d = q.data!;
  return (
    <Card title="Дневной лимит отправки">
      <p className="muted">
        Ограничение поверх прогрева. Работает только вниз: если прогрев сегодня
        разрешает меньше, действует его число — поднять выше нельзя, иначе
        репутация домена страдает. Пусто = без ручного ограничения.
      </p>
      <label className="field" style={{ maxWidth: 320 }}>
        общий потолок для всех ящиков
        <input type="number" min={0} placeholder={d.all === null ? "не задан" : String(d.all)}
               value={all} onChange={(e) => setAll(e.target.value)} />
      </label>
      <div className="table-wrap">
        <table className="data-table dense">
          <thead><tr>
            <th>Ящик</th><th>День прогрева</th><th>Можно сегодня</th>
            <th>Отправлено</th><th>Свой потолок</th>
          </tr></thead>
          <tbody>{d.mailboxes.map((m) => (
            <tr key={m.mailbox_id}>
              <td>{m.from_name || m.mailbox_id}
                <div className="muted small">{m.mailbox_id}</div></td>
              <td>{m.ramp_day}</td>
              <td>{m.effective_limit}</td>
              <td>{m.sent_today}</td>
              <td>
                <input type="number" min={0} style={{ width: 80 }}
                       placeholder={m.override === null || m.override === undefined
                         ? "по общему" : String(m.override)}
                       value={draft[m.mailbox_id] ?? ""}
                       onChange={(e) => setDraft({ ...draft, [m.mailbox_id]: e.target.value })} />
              </td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="actions">
        <button className="btn btn-primary" disabled={save.isPending}
                onClick={() => save.mutate()}>Сохранить лимиты</button>
      </div>
    </Card>
  );
}

/** Тумблер автоответчика. Раньше включался строкой в конфиге при старте службы,
 *  то есть выключить из панели было нельзя. Теперь проверяется на каждом
 *  входящем письме — выключил, и новых черновиков ответа больше нет. */
function AutoresponderCard() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["autoresponder"], queryFn: () => api.autoresponder() });
  const set = useMutation({
    mutationFn: (v: boolean) => api.setAutoresponder(v),
    onSuccess: (r) => {
      toast("success", r.enabled ? "Автоответчик включён" : "Автоответчик выключен");
      qc.invalidateQueries({ queryKey: ["autoresponder"] });
    },
    onError: (e) => toast("error", `Автоответчик: ${(e as Error).message}`),
  });
  if (q.isLoading) return null;
  const d = q.data;
  return (
    <Card title="Автоответчик">
      <label className="switch-row">
        <input type="checkbox" className="switch" checked={!!d?.enabled}
               disabled={set.isPending}
               onChange={(e) => set.mutate(e.target.checked)} />
        <span>готовить черновики ответов на входящие письма</span>
      </label>
      <p className="muted">
        Ответы не уходят сами: черновик попадает в очередь подтверждений, шлёте вы.
        Выключение действует сразу, перезапуск не нужен.
      </p>
      {d && !d.available && <div className="soft-warn">{d.note}</div>}
    </Card>
  );
}

export function Mailboxes() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["readiness"], queryFn: () => api.mailboxesReadiness() });
  const rows = q.data?.mailboxes ?? [];
  // Пауза ящика была только в CLI: чтобы остановить ящик, приходилось идти в
  // консоль сервера. Причину спрашиваем всегда — она уходит в аудит.
  const pause = useMutation({
    mutationFn: (v: { id: string; paused: boolean; reason?: string }) =>
      api.pauseMailbox(v.id, v.paused, v.reason),
    onSuccess: (r) => {
      toast("success", `${r.mailbox_id}: ${r.paused ? "на паузе" : "снят с паузы"}`);
      qc.invalidateQueries({ queryKey: ["readiness"] });
      qc.invalidateQueries({ queryKey: ["send-limits"] });
    },
    onError: (e) => toast("error", `Пауза: ${e instanceof ApiError ? e.detail : (e as Error).message}`),
  });
  const pauseAll = useMutation({
    mutationFn: (v: { paused: boolean; reason?: string }) =>
      api.pauseAllMailboxes(v.paused, v.reason),
    onSuccess: (r) => {
      toast("success", r.paused ? "Отправка остановлена по всем ящикам"
                                : "Отправка возобновлена");
      qc.invalidateQueries({ queryKey: ["readiness"] });
    },
    onError: (e) => toast("error", `Стоп: ${(e as Error).message}`),
  });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  return (
    <div>
      <div className="page-head">
        <h1>Ящики</h1>
        <div className="muted">{rows.length} шт.</div>
        <div className="card-actions">
          <button className="btn btn-danger" disabled={pauseAll.isPending}
                  onClick={() => {
                    const reason = window.prompt(
                      "Остановить отправку по ВСЕМ ящикам. Причина:");
                    if (reason && reason.trim()) pauseAll.mutate({ paused: true, reason });
                  }}>Остановить всё</button>
          <button className="btn" disabled={pauseAll.isPending}
                  onClick={() => pauseAll.mutate({ paused: false })}>
            Снять паузу со всех
          </button>
        </div>
      </div>
      <SendingWindowCard />
      <SendLimitsCard />
      <AutoresponderCard />
      <OutOfBaseToggleCard />
      <div className="table-wrap">
        <table className="data-table">
          <thead><tr><th>Ящик</th><th>Готов</th><th>День прогрева</th><th>Можно сегодня</th><th>Отправлено</th><th>Пауза</th></tr></thead>
          <tbody>{rows.map((m) => (
            <tr key={m.mailbox_id}><td>{m.mailbox_id}</td>
              <td><ReadyBadge ready={m.ready} reasons={m.reasons} /></td>
              <td>{m.ramp_day}</td><td>{m.daily_limit}</td><td>{m.sent_today}</td>
              <td>
                {m.paused
                  ? <button className="btn btn-sm" disabled={pause.isPending}
                            onClick={() => pause.mutate({ id: m.mailbox_id, paused: false })}>
                      снять паузу
                    </button>
                  : <button className="btn btn-sm btn-ghost danger" disabled={pause.isPending}
                            onClick={() => {
                              const reason = window.prompt(`Пауза ящика ${m.mailbox_id}. Причина:`);
                              if (reason && reason.trim())
                                pause.mutate({ id: m.mailbox_id, paused: true, reason });
                            }}>
                      поставить на паузу
                    </button>}
              </td></tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}

// ---- Экран «Ёмкость пулов» ----
export function Capacity() {
  const q = useQuery({ queryKey: ["capacity"], queryFn: () => api.capacity() });
  const rows = q.data?.pools ?? [];
  const ждёт = q.data?.ozhidaet;
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  return (
    <div>
      <div className="page-head"><h1>Ёмкость пулов</h1></div>
      {/* Ожидающие — владелец 20.08: «сколько ожидает отправки сегодня».
          Таблица показывала только израсходованное, и было не видно, есть ли
          чем занимать свободную ёмкость. По пулам не раскладываем: у ждущего
          письма ящика ещё нет, он назначается в момент захвата. */}
      {ждёт && (ждёт.vsego > 0 || ждёт.na_podtverzhdenii > 0) && (
        <div className="ozhidaet">
          Ожидает отправки: <b>{ждёт.vsego}</b>
          {ждёт.na_segodnya > 0 && <> · на сегодня {ждёт.na_segodnya}</>}
          {ждёт.v_polyote > 0 && <> · в отправке {ждёт.v_polyote}</>}
          {ждёт.prosrocheno > 0 && (
            <> · <span className="danger">просрочено {ждёт.prosrocheno}</span></>
          )}
          {ждёт.na_budushchee > 0 && <> · на будущее {ждёт.na_budushchee}</>}
          {ждёт.na_podtverzhdenii > 0 && (
            <> · ждут подтверждения {ждёт.na_podtverzhdenii}</>
          )}
        </div>
      )}
      {rows.length === 0 ? <Empty /> : (
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>Пул</th><th>Ящиков</th><th>Ёмкость</th><th>Отправлено</th><th>Свободно</th><th>Загрузка</th><th>Пауз</th></tr></thead>
            <tbody>{rows.map((p) => (
              <tr key={p.pool}><td>{p.pool}</td><td>{p.mailbox_count}</td><td>{p.daily_capacity}</td>
                <td>{p.sent_today}</td><td>{p.remaining_today}</td><td>{pct(p.utilization_pct)}</td>
                <td>{p.paused_mailboxes}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---- Экран 9: Моя статистика (агрегация /leads на клиенте) ----
export function MyStats() {
  const { principal } = useAuth();
  const q = useQuery({
    queryKey: ["my-leads-stats", principal?.user_id],
    queryFn: () => api.leads({ assigned_to: principal!.user_id, limit: 500 }),
    enabled: !!principal,
  });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  const leads = q.data!.leads;
  const by: Record<string, number> = {};
  for (const l of leads) by[l.status] = (by[l.status] || 0) + 1;
  return (
    <div>
      <div className="page-head"><h1>Моя статистика</h1></div>
      <Card title={`Всего лидов: ${leads.length}`}>
        <div className="metrics">
          {["taken", "called", "qualified", "not_qualified", "in_bitrix"].map((s) => (
            <div className="metric" key={s}><div className="metric-value">{by[s] || 0}</div>
              <div className="metric-label"><StatusBadge status={s} /></div></div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ---- Экран 22: Профиль (+смена пароля) ----
export function Profile() {
  const { principal, logout } = useAuth();
  const toast = useToast();
  const [pw, setPw] = useState({ old: "", neu: "" });
  const change = useMutation({
    mutationFn: () => api.changePassword(pw.old, pw.neu),
    onSuccess: async () => {
      toast("success", "Пароль изменён — войдите заново");
      await logout();
    },
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : "Ошибка"),
  });
  return (
    <div>
      <div className="page-head"><h1>Профиль</h1></div>
      <Card>
        <dl className="kv">
          <dt>Пользователь</dt><dd>{principal?.username}</dd>
          <dt>ID</dt><dd>{principal?.user_id}</dd>
          <dt>Роль</dt><dd>{principal?.role === "owner" ? "владелец" : "менеджер"}</dd>
        </dl>
      </Card>
      <Card title="Смена пароля">
        <div className="add-step">
          <input type="password" placeholder="текущий пароль" value={pw.old}
                 onChange={(e) => setPw({ ...pw, old: e.target.value })} />
          <input type="password" placeholder="новый пароль (8+)" value={pw.neu}
                 onChange={(e) => setPw({ ...pw, neu: e.target.value })} />
          <button className="btn btn-primary" disabled={!pw.old || pw.neu.length < 8 || change.isPending}
                  onClick={() => change.mutate()}>Сменить</button>
        </div>
        <p className="muted small">Смена пароля разрывает остальные сессии (ФЗ-152 безопасность).</p>
      </Card>
    </div>
  );
}

// ---- Экран «Отправленные письма» ----
// Владелец 11.08: «последний пункт переименуй в отправленные письма, и туда
// положи всё, что отправили мы». Общего списка отправленного в панели не было:
// письмо открывалось поштучно или всплывало в карточке лида, а вопрос «этому мы
// уже писали?» решался памятью оператора. На месте «Прогрева» — он всё равно
// под холдом и показывать там нечего.
export function Otpravlennye() {
  const [q, setQ] = useState("");
  const [ищем, setИщем] = useState("");
  const [tolkoOtvet, setTolkoOtvet] = useState(false);
  // Направление: «» — оба. Владелец 20.08 просил колонку и выбор, потому что
  // КЦ и Мейер ведут разные менеджеры и смотреть их вперемешку неудобно.
  const [napravlenie, setNapravlenie] = useState("");
  const [offset, setOffset] = useState(0);
  // Какое письмо раскрыто. Одно за раз: список длинный, и раскрытые вперемешку
  // читаются хуже, чем одно письмо целиком.
  const [открыто, setОткрыто] = useState<number | null>(null);
  const PAGE = 100;

  const данные = useQuery({
    queryKey: ["otpravlennye", ищем, tolkoOtvet, napravlenie, offset],
    queryFn: () => api.otpravlennye({
      q: ищем || undefined, replied: tolkoOtvet || undefined,
      napravlenie: napravlenie || undefined,
      limit: PAGE, offset,
    }),
  });

  if (данные.isLoading) return <Spinner />;
  if (данные.error) return <ErrorBox error={данные.error} />;
  const письма = данные.data?.pisma ?? [];
  const всего = данные.data?.vsego ?? 0;

  return (
    <div>
      <div className="page-head">
        <h1>Отправленные письма</h1>
        <div className="muted">всего {всего}</div>
      </div>

      <div className="filterbar">
        <input placeholder="адрес, компания, ИНН или тема" value={q}
               style={{ minWidth: 260 }}
               onChange={(e) => setQ(e.target.value)}
               onKeyDown={(e) => {
                 if (e.key === "Enter") { setOffset(0); setИщем(q.trim()); }
               }} />
        <button className="btn" onClick={() => { setOffset(0); setИщем(q.trim()); }}>
          найти
        </button>
        <select value={napravlenie} title="направление"
                onChange={(e) => { setOffset(0); setNapravlenie(e.target.value); }}>
          <option value="">оба направления</option>
          <option value="kc">Компрессор Центр</option>
          <option value="meyer">Meyer</option>
        </select>
        <label>
          <input type="checkbox" checked={tolkoOtvet}
                 onChange={(e) => { setOffset(0); setTolkoOtvet(e.target.checked); }} />
          {" "}только те, кто ответил
        </label>
      </div>

      {письма.length === 0 ? (
        <Empty hint="Отправленных писем пока нет" />
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Когда</th><th>Кому</th><th>Компания</th><th>Напр.</th>
                <th>Тема</th><th>С ящика</th><th>Чем кончилось</th>
              </tr>
            </thead>
            <tbody>
              {письма.map((м) => (
                <SentRow key={м.id} m={м}
                         open={открыто === м.id}
                         onToggle={() => setОткрыто(открыто === м.id ? null : м.id)} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pager offset={offset} shown={письма.length} unit="писем"
             onPrev={() => setOffset(Math.max(0, offset - PAGE))}
             onNext={() => setOffset(offset + PAGE)} />
    </div>
  );
}


/** Есть ли в теле настоящая разметка. Если нет — это простой текст, и рисовать
 *  его надо как текст: в innerHTML переводы строк пропадают. */
function похоже_на_html(t: string): boolean {
  return /<(p|div|br|table|tr|td|span|a|ul|ol|li|h[1-6]|img|body|html)\b[^>]*>/i
    .test(String(t || ""));
}

/** Строка списка отправленного: щелчок раскрывает письмо целиком.
 *  Владелец 11.08: «а как открыть сами письма то» — список показывал тему и
 *  исход, а текста письма достать было негде, хотя движок его отдаёт. */
function SentRow({ m, open, onToggle }: {
  m: SentMessage; open: boolean; onToggle: () => void;
}) {
  const письмо = useQuery({
    queryKey: ["pismo", m.id],
    queryFn: () => api.pismoCelikom(m.id),
    enabled: open,          // тело тянем только когда открыли
  });
  return (
    <>
      <tr className={(m.otbivok > 0 ? "row-bad " : "") + "row-click"}
          onClick={onToggle} title="показать письмо целиком">
        <td className="nowrap">{fmtDate(m.sent_at)}</td>
        <td>{m.email || "—"}</td>
        <td>
          {m.company_name || "—"}
          {m.inn && <div className="muted small">{m.inn}</div>}
        </td>
        <td className="nowrap">
          <span className={"napr napr-" + (m.napravlenie || "kc")}>
            {m.napravlenie === "meyer" ? "Meyer" : "КЦ"}
          </span>
        </td>
        <td>
          <span className="sent-caret">{open ? "▾" : "▸"}</span>{" "}
          {m.subject || "—"}
        </td>
        <td className="muted small">{m.mailbox_id || "—"}</td>
        <td>
          {m.otbivok > 0 && <span className="danger">отбилось</span>}
          {m.otvetov > 0 && (
            <span className="badge badge-qualified">
              ответили{m.otvetov > 1 ? ` · ${m.otvetov}` : ""}
            </span>
          )}
          {m.otbivok === 0 && m.otvetov === 0 && (
            <span className="muted small">тишина</span>
          )}
        </td>
      </tr>
      {open && (
        <tr className="sent-body-row">
          <td colSpan={7}>
            {письмо.isLoading && <Spinner />}
            {письмо.error && <ErrorBox error={письмо.error} />}
            {письмо.data && (
              <div className="sent-body">
                <div className="muted small">
                  {письмо.data.mailbox_id} → {письмо.data.email}
                  {письмо.data.contact_name ? ` · ${письмо.data.contact_name}` : ""}
                  {" · "}{fmtDate(письмо.data.sent_at)}
                  {/* Откуда взят текст — честно: у писем, отправленных вживую
                      из панели, body_rendered пуст, и тело поднимается из
                      решения оператора. */}
                  {письмо.data.body_source
                    ? ` · текст из: ${письмо.data.body_source}` : ""}
                </div>
                <div className="sent-subject">{письмо.data.subject}</div>
                {письмо.data.body_missing ? (
                  <p className="soft-warn">
                    тела письма в базе нет — так бывает у писем, отправленных
                    вживую из панели до 28.07
                  </p>
                ) : похоже_на_html(письмо.data.body) ? (
                  <div className="sent-html"
                       dangerouslySetInnerHTML={{ __html: письмо.data.body }} />
                ) : (
                  /* Тело у наших писем — обычный текст с переводами строк, а
                     он уходил в innerHTML, где переносы схлопываются: письмо
                     показывалось сплошной простынёй (владелец 20.08). */
                  <pre className="sent-text">{письмо.data.body}</pre>
                )}
                {m.otvetov > 0 && m.recipient_id && (
                  <p className="muted small">
                    на это письмо ответили — ответ ищите в ленте лидов
                  </p>
                )}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

// ---- Экран «Загрузить базу» ----
// Владелец 11.08: «сделай кнопку для загрузки ручной такой базы в панель,
// чтобы я мог создать компанию и загрузить новые емайлы + сгенерировать
// очередь писем». До этого база пополнялась только серверными скриптами —
// каждая новая партия ждала меня.
//
// Два шага намеренно разделены. Сначала разбор без записи: видно, сколько
// адресов новых, сколько уже есть и сколько в стоп-листе. Загрузка вслепую —
// это способ написать тому, кто просил не писать.
export function ZagruzkaBazy() {
  const toast = useToast();
  const [имя, setИмя] = useState("");
  const [текст, setТекст] = useState("");
  const [группа, setГруппа] = useState("");
  const [свод, setСвод] = useState<null | Awaited<ReturnType<typeof api.importBazy>>>(null);

  const разбор = useMutation({
    mutationFn: () => api.importBazy({ text: текст, name: имя, dry_run: true }),
    onSuccess: (r) => setСвод(r),
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : "Ошибка"),
  });
  const загрузка = useMutation({
    mutationFn: () => api.importBazy({ text: текст, name: имя, group: группа.trim(),
                                       dry_run: false }),
    onSuccess: (r) => {
      setСвод(r);
      toast("success", `В группу «${r.zapisano?.gruppa}»: добавлено `
                       + `${r.zapisano?.dobavleno}, обновлено ${r.zapisano?.obnovleno}`);
    },
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : "Ошибка"),
  });

  function взятьФайл(f: File | undefined) {
    if (!f) return;
    setИмя(f.name);
    setСвод(null);
    const r = new FileReader();
    r.onload = () => setТекст(String(r.result || ""));
    // Файл читает браузер, а не сервер: так не нужен multipart, которого на
    // сервере может не оказаться, и загрузка не падает на отсутствии пакета.
    r.readAsText(f, "utf-8");
  }

  return (
    <div>
      <div className="page-head"><h1>Загрузить базу</h1></div>

      <Card title="Файл партии">
        <p className="muted small">
          Понимаются две формы: обогащённый JSONL (строка на компанию, адреса в
          поле emails) и CSV выгрузок (строка на контакт, разделитель ; или ,).
          Компании, помеченные как конкуренты, не загружаются.
        </p>
        <input type="file" accept=".jsonl,.json,.csv,.txt"
               onChange={(e) => взятьФайл(e.target.files?.[0])} />
        {имя && (
          <p className="muted small">
            {имя} · {(текст.length / 1024).toFixed(0)} КБ
          </p>
        )}
        <div style={{ marginTop: 8 }}>
          <button className="btn btn-primary" disabled={!текст || разбор.isPending}
                  onClick={() => разбор.mutate()}>
            Разобрать (пока без записи)
          </button>
        </div>
      </Card>

      {свод && (
        <Card title="Что получится">
          <div className="kv-list">
            <div className="kv-row"><span className="kv-key">строк в файле</span>
              <span className="kv-val">{свод.vsego_strok}</span></div>
            <div className="kv-row"><span className="kv-key">уникальных адресов</span>
              <span className="kv-val">{свод.unikalnyh_adresov}</span></div>
            <div className="kv-row"><span className="kv-key">уже есть в базе</span>
              <span className="kv-val">{свод.uzhe_v_baze}</span></div>
            <div className="kv-row"><span className="kv-key">в стоп-листе</span>
              <span className="kv-val">{свод.v_stop_liste}</span></div>
            <div className="kv-row"><span className="kv-key">без ИНН</span>
              <span className="kv-val">{свод.bez_inn}</span></div>
            <div className="kv-row"><span className="kv-key"><b>к загрузке</b></span>
              <span className="kv-val"><b>{свод.k_zagruzke}</b></span></div>
          </div>
          {свод.zamechaniya?.length > 0 && (
            <ul className="muted small">
              {свод.zamechaniya.map((з, i) => <li key={i}>{з}</li>)}
            </ul>
          )}
          {свод.primery?.length > 0 && (
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th>Адрес</th><th>Компания</th><th>ИНН</th><th>Кто</th></tr></thead>
                <tbody>
                  {свод.primery.map((п, i) => (
                    <tr key={i}>
                      <td>{п.email}</td><td>{п.company_name || "—"}</td>
                      <td>{п.inn || "—"}</td>
                      <td>{[п.contact_name, п.role].filter(Boolean).join(" · ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {свод.zapisano ? (
            <p>
              Записано в группу <b>{свод.zapisano.gruppa}</b>: добавлено{" "}
              {свод.zapisano.dobavleno}, обновлено {свод.zapisano.obnovleno}
              {свод.zapisano.propushcheno > 0
                ? `, пропущено ${свод.zapisano.propushcheno}` : ""}.{" "}
              <Link to="/confirm">Перейти в очередь и сгенерировать письма</Link>
            </p>
          ) : (
            <div style={{ marginTop: 10 }}>
              <label>
                группа (она же направление в очереди):{" "}
                <input value={группа} placeholder="например: пищевая-2026-08"
                       style={{ minWidth: 240 }}
                       onChange={(e) => setГруппа(e.target.value)} />
              </label>{" "}
              <button className="btn btn-primary"
                      disabled={!группа.trim() || свод.k_zagruzke === 0
                                || загрузка.isPending}
                      onClick={() => загрузка.mutate()}>
                Загрузить {свод.k_zagruzke} в базу
              </button>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
