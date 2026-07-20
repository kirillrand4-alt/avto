// Живые экраны-таблицы над реальными эндпоинтами: кампании, логи, репутация,
// suppression, ящики, ёмкость, моя статистика, профиль.

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { useAuth } from "../context/auth";
import { useToast } from "../components/Toast";
import { Spinner, ErrorBox, Empty, Card, StatusBadge, ReadyBadge } from "../components/ui";
import { fmtDate, pct, maskEmail } from "../lib/format";

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
      {rows.length === 0 ? <Empty hint="Создайте кампанию через CLI: python -m sender campaign-create" /> : (
        <table className="data-table">
          <thead><tr><th>#</th><th>Название</th><th>Статус</th><th>Юрлицо</th><th>Создана</th></tr></thead>
          <tbody>{rows.map((c) => (
            <tr key={c.id}><td>{c.id}</td><td>{c.name}</td><td><StatusBadge status={c.status} kind="campaign" /></td>
              <td>{c.legal_entity}</td><td>{fmtDate(c.created_at)}</td></tr>
          ))}</tbody>
        </table>
      )}
    </div>
  );
}

// ---- Экран 18: Логи событий ----
export function Logs() {
  const [type, setType] = useState("");
  const q = useQuery({ queryKey: ["events", type], queryFn: () => api.events({ event_type: type || undefined, limit: 200 }) });
  const rows = q.data?.events ?? [];
  return (
    <div>
      <div className="page-head"><h1>Логи событий</h1></div>
      <div className="filterbar">
        <label>Тип
          <select value={type} onChange={(e) => setType(e.target.value)}>
            {["", "sent", "delivered", "bounce", "complaint", "reply", "unsubscribe", "suppress"].map((t) =>
              <option key={t} value={t}>{t || "все"}</option>)}
          </select>
        </label>
      </div>
      {q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} /> :
        rows.length === 0 ? <Empty /> : (
          <table className="data-table">
            <thead><tr><th>#</th><th>Тип</th><th>Кампания</th><th>Провайдер</th><th>Ящик</th><th>Время</th></tr></thead>
            <tbody>{rows.map((e) => (
              <tr key={e.id}><td>{e.id}</td><td><StatusBadge status={e.event_type} kind="campaign" /></td>
                <td>{e.campaign_id ?? "—"}</td><td>{e.provider ?? "—"}</td><td>{e.mailbox_id ?? "—"}</td>
                <td>{fmtDate(e.event_ts)}</td></tr>
            ))}</tbody>
          </table>
        )}
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
          <table className="data-table">
            <thead><tr><th>Скоуп</th><th>Цель</th><th>Метрика</th><th>Значение</th><th>Порог</th></tr></thead>
            <tbody>{trips.map((t, i) => (
              <tr key={i} className="row-hot"><td>{t.scope}</td><td>{t.target}</td><td>{t.metric}</td>
                <td className="danger">{pct(t.value)}</td><td>{pct(t.threshold)}</td></tr>
            ))}</tbody>
          </table>
        )}
      </Card>
      <Card title="Динамика 7 дней (global)">
        {series.isLoading ? <Spinner /> : pts.length === 0 ? <Empty /> : (
          <table className="data-table">
            <thead><tr><th>День</th><th>Отпр.</th><th>Bounce</th><th>Жалобы</th><th>Ответы</th><th>BR%</th><th>CR%</th></tr></thead>
            <tbody>{pts.map((p, i) => (
              <tr key={i}><td>{p.target}</td><td>{p.sent}</td><td>{p.bounce}</td><td>{p.complaint}</td>
                <td>{p.reply}</td><td>{pct(p.bounce_rate)}</td><td>{pct(p.complaint_rate)}</td></tr>
            ))}</tbody>
          </table>
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
  const q = useQuery({ queryKey: ["suppression", scope], queryFn: () => api.suppression({ scope: scope || undefined, limit: 200 }) });
  const rm = useMutation({
    mutationFn: (sid: number) => api.removeSuppression(sid, "operator removal"),
    onSuccess: () => { toast("success", "Удалено (записано в аудит)"); qc.invalidateQueries({ queryKey: ["suppression"] }); },
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : "Ошибка"),
  });
  const rows = q.data?.suppression ?? [];
  return (
    <div>
      <div className="page-head"><h1>Suppression (ФЗ-152)</h1></div>
      <div className="filterbar">
        <label>Скоуп
          <select value={scope} onChange={(e) => setScope(e.target.value)}>
            {["", "email", "domain", "inn"].map((s) => <option key={s} value={s}>{s || "все"}</option>)}
          </select>
        </label>
      </div>
      {q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} /> :
        rows.length === 0 ? <Empty /> : (
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
        )}
    </div>
  );
}

// ---- Экран 15: Ящики и готовность ----
export function Mailboxes() {
  const q = useQuery({ queryKey: ["readiness"], queryFn: () => api.mailboxesReadiness() });
  const rows = q.data?.mailboxes ?? [];
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  return (
    <div>
      <div className="page-head"><h1>Ящики</h1><div className="muted">{rows.length} шт.</div></div>
      <table className="data-table">
        <thead><tr><th>Ящик</th><th>Готов</th><th>Рамп-день</th><th>Лимит/день</th><th>Отправлено</th><th>Пауза</th></tr></thead>
        <tbody>{rows.map((m) => (
          <tr key={m.mailbox_id}><td>{m.mailbox_id}</td>
            <td><ReadyBadge ready={m.ready} reasons={m.reasons} /></td>
            <td>{m.ramp_day}</td><td>{m.daily_limit}</td><td>{m.sent_today}</td>
            <td>{m.paused ? "да" : "—"}</td></tr>
        ))}</tbody>
      </table>
    </div>
  );
}

// ---- Экран «Ёмкость пулов» ----
export function Capacity() {
  const q = useQuery({ queryKey: ["capacity"], queryFn: () => api.capacity() });
  const rows = q.data?.pools ?? [];
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  return (
    <div>
      <div className="page-head"><h1>Ёмкость пулов</h1></div>
      {rows.length === 0 ? <Empty /> : (
        <table className="data-table">
          <thead><tr><th>Пул</th><th>Ящиков</th><th>Ёмкость</th><th>Отправлено</th><th>Свободно</th><th>Загрузка</th><th>Пауз</th></tr></thead>
          <tbody>{rows.map((p) => (
            <tr key={p.pool}><td>{p.pool}</td><td>{p.mailbox_count}</td><td>{p.daily_capacity}</td>
              <td>{p.sent_today}</td><td>{p.remaining_today}</td><td>{pct(p.utilization_pct)}</td>
              <td>{p.paused_mailboxes}</td></tr>
          ))}</tbody>
        </table>
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

// ---- Экран 22: Профиль ----
export function Profile() {
  const { principal } = useAuth();
  return (
    <div>
      <div className="page-head"><h1>Профиль</h1></div>
      <Card>
        <dl className="kv">
          <dt>Пользователь</dt><dd>{principal?.username}</dd>
          <dt>ID</dt><dd>{principal?.user_id}</dd>
          <dt>Роль</dt><dd>{principal?.role === "owner" ? "владелец" : "менеджер"}</dd>
        </dl>
        <p className="muted small">Смена пароля/2FA/сессии — раздел «Настройки (бэклог)»: нужны POST /profile-эндпоинты.</p>
      </Card>
    </div>
  );
}
