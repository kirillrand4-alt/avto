// Экран 7 — Карточка лида. История переписки, действия: взять, сменить статус,
// нормализовать телефон, позвонить. Конкурентные действия ловят 409/400.

import { useState } from "react";
import { Link, useParams } from "react-router-dom";
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

  // #62: ответ прямо из карточки. Если робот уже подготовил черновик — ведём
  // в очередь подтверждений; свой текст оператора кладём туда же черновиком.
  const draft = useQuery({
    queryKey: ["lead-reply-draft", leadId],
    queryFn: () => api.leadReplyDraft(leadId),
    enabled: Number.isFinite(leadId),
  });
  const [replyOpen, setReplyOpen] = useState(false);
  const [replySubject, setReplySubject] = useState("");
  const [replyText, setReplyText] = useState("");
  const sendReply = useMutation({
    mutationFn: () => api.leadReply(leadId, {
      subject: replySubject || undefined, body: replyText }),
    onSuccess: (d) => {
      toast("success", `Черновик #${d.review_id} в очереди подтверждений`);
      setReplyOpen(false);
      setReplyText("");
      qc.invalidateQueries({ queryKey: ["lead-reply-draft", leadId] });
    },
    onError: (e) => toast("error", e instanceof ApiError
      ? `Не встало в очередь: ${e.detail}` : "Ошибка"),
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

      <Card title="Ответить на письмо">
        {draft.data?.draft ? (
          <p>
            Робот подготовил черновик ответа{" "}
            <b>#{draft.data.draft.id}</b> «{draft.data.draft.subject}» —{" "}
            <Link to="/confirm">открыть в очереди подтверждений</Link>{" "}
            <span className="muted">(найдите его поиском по адресу {lead.email})</span>
          </p>
        ) : (
          <p className="muted">Готового черновика нет — напишите свой текст,
            он встанет в очередь подтверждений и уйдёт в тред клиента.</p>
        )}
        {!replyOpen && (
          <button className="btn btn-primary" onClick={() => {
            setReplySubject("Re: " + (lead.company_name || ""));
            setReplyOpen(true);
          }}>Написать ответ</button>
        )}
        {replyOpen && (
          <div className="reply-box">
            <input className="reply-subject" value={replySubject}
                   placeholder="тема (Re: ...)"
                   onChange={(e) => setReplySubject(e.target.value)} />
            <textarea className="reply-text" rows={8} value={replyText}
                      placeholder="Текст ответа. Финал «С уважением,» допишется подписью отправки."
                      onChange={(e) => setReplyText(e.target.value)} />
            <div className="actions">
              <button className="btn btn-primary"
                      disabled={sendReply.isPending || !replyText.trim()}
                      onClick={() => sendReply.mutate()}>
                В очередь на отправку
              </button>
              <button className="btn btn-ghost" onClick={() => setReplyOpen(false)}>
                Отмена
              </button>
            </div>
          </div>
        )}
      </Card>

      <Card title={dialog.data?.scope === "company"
        ? "Переписка со всей компанией" : "Переписка"}>
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
            {it.email ? ` · ${it.email}` : ""}
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
