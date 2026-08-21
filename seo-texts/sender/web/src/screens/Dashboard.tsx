// Экран 2 — Дашборд (owner). Светофор репутации + глобальные метрики + активные
// гейты + ёмкость пулов + проблемные ящики. Всё из реальных эндпоинтов.

import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Spinner, ErrorBox, Card, TrafficLight, ReadyBadge } from "../components/ui";
import { pct } from "../lib/format";

export function Dashboard() {
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: () => api.dashboard(), refetchInterval: 30_000 });
  const gates = useQuery({ queryKey: ["gates"], queryFn: () => api.gatesActive(), refetchInterval: 30_000 });
  const cap = useQuery({ queryKey: ["capacity"], queryFn: () => api.capacity() });
  const mb = useQuery({ queryKey: ["readiness"], queryFn: () => api.mailboxesReadiness() });

  if (dash.isLoading) return <Spinner />;
  if (dash.error) return <ErrorBox error={dash.error} />;
  const g = dash.data!.global;
  const trips = gates.data?.trips ?? [];
  const notReady = (mb.data?.mailboxes ?? []).filter((m) => !m.ready);
  // Отказ почтовика — это НЕ отбивка: письмо не ушло вовсе, и виноват не
  // список, а мы (темп, домен, текст). Поэтому отдельная строка и отдельная
  // таблица: 21.08 три мейеровских домена придушили за час, а на экране это
  // никак не отражалось — отказ лежал только в messages.last_error.
  const rejectRows = (dash.data?.mailboxes ?? []).filter((m) => (m.rejected ?? 0) > 0);

  return (
    <div>
      <div className="page-head"><h1>Дашборд</h1></div>

      <Card>
        <div className="light-row">
          <TrafficLight complaintRate={g.global_complaint_rate} bounceRate={g.global_bounce_rate} />
          <div className="metrics">
            <Metric label="Отправлено" value={g.total_sent} />
            <Metric label="Bounce" value={`${g.total_bounced} (${pct(g.global_bounce_rate)})`} />
            <Metric label="Жалобы" value={`${g.total_complaints} (${pct(g.global_complaint_rate)})`} />
            <Metric label="Отклонено почтовиком" value={`${g.total_rejected ?? 0} (${pct(g.global_reject_rate ?? 0)})`} />
            <Metric label="Ящиков активно" value={g.active_mailboxes} />
            <Metric label="На паузе" value={g.paused_mailboxes} />
          </div>
        </div>
      </Card>

      <Card title={`Сработавшие гейты (${trips.length})`}>
        {trips.length === 0 ? <p className="muted">Гейты не сработали — репутация в норме.</p> : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Скоуп</th><th>Цель</th><th>Метрика</th><th>Значение</th><th>Порог</th></tr></thead>
              <tbody>
                {trips.map((t, i) => (
                  <tr key={i} className="row-hot">
                    <td>{t.scope}</td><td>{t.target}</td><td>{t.metric}</td>
                    <td className="danger">{pct(t.value)}</td><td>{pct(t.threshold)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Ёмкость пулов">
        {(cap.data?.pools ?? []).length === 0 ? <p className="muted">Нет пулов.</p> : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Пул</th><th>Ящиков</th><th>Ёмкость/день</th><th>Отправлено</th><th>Свободно</th><th>Загрузка</th></tr></thead>
              <tbody>
                {cap.data!.pools.map((p) => (
                  <tr key={p.pool}>
                    <td>{p.pool}</td><td>{p.mailbox_count}</td><td>{p.daily_capacity}</td>
                    <td>{p.sent_today}</td><td>{p.remaining_today}</td><td>{pct(p.utilization_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title={`Отклонено почтовиком по ящикам (${rejectRows.length})`}>
        {rejectRows.length === 0 ? (
          <p className="muted">Отказов нет — почтовик принимает все письма.</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Ящик</th><th>Отклонено</th><th>Ушло сегодня</th><th>Доля отказов</th><th>Пауза</th></tr></thead>
              <tbody>
                {rejectRows.map((m) => (
                  <tr key={m.mailbox_id} className="row-hot">
                    <td>{m.mailbox_id}</td>
                    <td className="danger">{m.rejected}</td>
                    <td>{m.sent_today}</td>
                    <td className="danger">{pct(m.reject_rate ?? 0)}</td>
                    <td>{m.paused ? "на паузе" : "шлёт"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title={`Проблемные ящики (${notReady.length})`}>
        {notReady.length === 0 ? <p className="muted">Все ящики в норме.</p> : (
          <ul className="plain">
            {notReady.map((m) => (
              <li key={m.mailbox_id}>{m.mailbox_id} — <ReadyBadge ready={m.ready} reasons={m.reasons} /></li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: unknown }) {
  return <div className="metric"><div className="metric-value">{String(value)}</div><div className="metric-label">{label}</div></div>;
}
