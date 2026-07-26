// Экран 7 — Карточка лида. История переписки, действия: взять, сменить статус,
// нормализовать телефон, позвонить. Конкурентные действия ловят 409/400.

import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { useToast } from "../components/Toast";
import { Spinner, ErrorBox, StatusBadge, Card } from "../components/ui";
import { fmtDate, normalizePhone, replyBadge } from "../lib/format";
import type { DialogItem } from "../api/types";

const NEXT_STATUS = [
  { key: "called", label: "Позвонил" },
  { key: "qualified", label: "Квалифицирован" },
  { key: "not_qualified", label: "Не квалифицирован" },
  { key: "in_bitrix", label: "Передан в Bitrix" },
];

export function LeadCard() {
  const { id } = useParams();
  const leadId = Number(id);
  const qc = useQueryClient();
  const toast = useToast();

  const q = useQuery({
    queryKey: ["lead", leadId],
    queryFn: () => api.lead(leadId),
    enabled: Number.isFinite(leadId),
  });

  // Настоящая переписка: наши письма + ответы клиента. Раньше карточка
  // показывала только журнал смены статусов под заголовком «История
  // переписки» — прочитать, что ответил клиент, было негде.
  const dialog = useQuery({
    queryKey: ["lead-dialog", leadId],
    queryFn: () => api.leadDialog(leadId),
    enabled: Number.isFinite(leadId),
  });

  const take = useMutation({
    mutationFn: () => api.takeLead(leadId),
    onSuccess: () => { toast("success", "Лид ваш"); qc.invalidateQueries({ queryKey: ["lead", leadId] }); },
    onError: (e) => toast("error", e instanceof ApiError && (e.status === 409 || e.status === 400)
      ? "Уже взял другой" : "Ошибка"),
  });

  const setStatus = useMutation({
    mutationFn: (status: string) => api.setLeadStatus(leadId, status),
    onSuccess: () => { toast("success", "Статус обновлён"); qc.invalidateQueries({ queryKey: ["lead", leadId] }); },
    onError: (e) => toast("error", e instanceof ApiError && e.status === 409
      ? "Лид изменён другим — обновите" : (e instanceof ApiError ? e.detail : "Ошибка")),
  });

  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  const lead = q.data!.lead;
  const rb = replyBadge(lead.reply_kind);
  const normPhone = normalizePhone(lead.phone);

  return (
    <div className="lead-card">
      <div className="page-head">
        <h1>{lead.company_name || lead.email}</h1>
        <StatusBadge status={lead.status} />
      </div>

      <div className="lead-grid">
        <Card title="Контакт">
          <dl className="kv">
            <dt>Email</dt><dd>{lead.email}</dd>
            <dt>ИНН</dt><dd>{lead.inn || "—"}</dd>
            <dt>Телефон</dt><dd>{lead.phone || "—"}{normPhone && normPhone !== lead.phone && <span className="muted"> → {normPhone}</span>}</dd>
            <dt>Приоритет</dt><dd><span className={`reply reply-${rb.cls}`}>{rb.icon} {rb.label}</span></dd>
            <dt>Потребность</dt><dd>{lead.need || "—"}</dd>
            <dt>Bitrix</dt><dd>{lead.bitrix_lead_id ? `#${lead.bitrix_lead_id}` : "не передан"}</dd>
            <dt>Создан</dt><dd>{fmtDate(lead.created_at)}</dd>
          </dl>
          <div className="actions">
            {normPhone && <a className="btn btn-primary" href={`tel:${normPhone}`}>Позвонить {normPhone}</a>}
            {lead.assigned_to == null && <button className="btn btn-take" onClick={() => take.mutate()} disabled={take.isPending}>Взять</button>}
          </div>
        </Card>

        <Card title="Действия по лиду">
          {lead.assigned_to == null
            ? <p className="muted">Возьмите лид, чтобы менять статус.</p>
            : (
              <div className="status-actions">
                {NEXT_STATUS.map((s) => (
                  <button key={s.key} className="btn" disabled={setStatus.isPending || lead.status === s.key}
                          onClick={() => setStatus.mutate(s.key)}>{s.label}</button>
                ))}
              </div>
            )}
          <p className="muted small">version={lead.version} · SLA {fmtDate(lead.sla_due_at)}</p>
        </Card>
      </div>

      <Card title="Переписка">
        {dialog.isLoading ? <Spinner />
          : dialog.error ? <ErrorBox error={dialog.error} />
          : <Dialog items={dialog.data?.thread || []} />}
      </Card>

      <Card title="Журнал действий">
        <History items={q.data!.history} />
      </Card>
    </div>
  );
}

/** Одно событие переписки: наше письмо или ответ клиента. */
const KIND_RU: Record<string, string> = {
  sent: "мы написали",
  reply: "ответ клиента",
  reply_auto: "автоответ клиента",
  complaint: "жалоба",
  bounce: "письмо не доставлено",
  dsn: "отчёт о доставке",
};

function Dialog({ items }: { items: DialogItem[] }) {
  if (!items.length) {
    return <p className="muted">Писем и ответов пока нет.</p>;
  }
  return (
    <div className="dialog">
      {items.map((it, i) => (
        <div key={i} className={`dialog-item dialog-${it.direction}`}>
          <div className="muted small">
            {KIND_RU[it.kind] || it.kind} · {fmtDate(it.ts)}
            {it.mailbox_id ? ` · ящик ${it.mailbox_id}` : ""}
            {it.status ? ` · ${it.status}` : ""}
          </div>
          {it.subject && <div><b>{it.subject}</b></div>}
          {it.body && <pre className="confirm-letter">{it.body}</pre>}
        </div>
      ))}
    </div>
  );
}

function History({ items }: { items: unknown[] }) {
  if (!items || items.length === 0) return <p className="muted">Нет записей истории.</p>;
  return (
    <ul className="history">
      {items.map((it, i) => (
        <li key={i}><pre>{typeof it === "string" ? it : JSON.stringify(it, null, 1)}</pre></li>
      ))}
    </ul>
  );
}
