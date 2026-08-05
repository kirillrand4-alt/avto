// Экран 7 — Карточка лида. История переписки, действия: взять, сменить статус,
// нормализовать телефон, позвонить. Конкурентные действия ловят 409/400.

import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { useToast } from "../components/Toast";
import { Spinner, ErrorBox, StatusBadge, Card } from "../components/ui";
import { fmtDate, normalizePhone, replyBadge } from "../lib/format";
import type { DialogItem, DialogThread } from "../api/types";

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
  // ключ ветки, в которой открыта форма ответа (null — закрыта). Раньше это был
  // булев флаг на всю карточку: форма висела сверху и не знала, на какое письмо
  // отвечает.
  const [replyOpen, setReplyOpen] = useState<string | null>(null);
  const [replySubject, setReplySubject] = useState("");
  const [replyText, setReplyText] = useState("");
  const sendReply = useMutation({
    mutationFn: () => api.leadReply(leadId, {
      subject: replySubject || undefined, body: replyText }),
    onSuccess: (d) => {
      toast("success", `Черновик #${d.review_id} в очереди подтверждений`);
      setReplyOpen(null);
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

      {draft.data?.draft && (
        <Card title="Черновик ответа готов">
          <p>
            Робот подготовил черновик{" "}
            <b>#{draft.data.draft.id}</b> «{draft.data.draft.subject}» —{" "}
            <Link to="/confirm">открыть в очереди подтверждений</Link>{" "}
            <span className="muted">(найдите его поиском по адресу {lead.email})</span>
          </p>
        </Card>
      )}

      {/* Ветки переписки. Владелец 27.07: лента обрывалась, а кнопка ответа
          висела СВЕРХУ, хотя отвечают на нижнее письмо. Теперь каждая ветка —
          отдельная карточка, а форма ответа стоит ПОД последним письмом своей
          ветки, с темой, подставленной из этой же ветки. */}
      {dialog.isLoading ? <Card title="Переписка"><Spinner /></Card>
        : dialog.error ? <Card title="Переписка"><ErrorBox error={dialog.error} /></Card>
        : <Threads
            threads={dialog.data?.threads || []}
            fallback={dialog.data?.thread || []}
            scope={dialog.data?.scope}
            replyOpenKey={replyOpen}
            onOpenReply={(key, subject) => {
              setReplySubject(subject ? "Re: " + subject
                : "Re: " + (lead.company_name || ""));
              setReplyText("");
              setReplyOpen(key);
            }}
            onCancel={() => setReplyOpen(null)}
            replySubject={replySubject}
            setReplySubject={setReplySubject}
            replyText={replyText}
            setReplyText={setReplyText}
            sending={sendReply.isPending}
            onSend={() => sendReply.mutate()}
          />}

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

/** Форма ответа — та же разметка, что была, но живёт ВНУТРИ ветки. */
function ReplyBox(p: {
  subject: string; setSubject: (s: string) => void;
  text: string; setText: (s: string) => void;
  sending: boolean; onSend: () => void; onCancel: () => void;
}) {
  return (
    <div className="reply-box">
      <input className="reply-subject" value={p.subject}
             placeholder="тема (Re: ...)"
             onChange={(e) => p.setSubject(e.target.value)} />
      <textarea className="reply-text" rows={8} value={p.text}
                placeholder="Текст ответа. Финал «С уважением,» допишется подписью отправки."
                onChange={(e) => p.setText(e.target.value)} />
      <div className="actions">
        <button className="btn btn-primary"
                disabled={p.sending || !p.text.trim()}
                onClick={p.onSend}>В очередь на отправку</button>
        <button className="btn btn-ghost" onClick={p.onCancel}>Отмена</button>
      </div>
    </div>
  );
}

/** Переписка по ВЕТКАМ. Если бэк ещё не отдаёт threads (старый сервер) —
 *  показываем плоский список, как раньше, чтобы экран не опустел. */
function Threads(p: {
  threads: DialogThread[]; fallback: DialogItem[]; scope?: string;
  replyOpenKey: string | null;
  onOpenReply: (key: string, subject: string) => void;
  onCancel: () => void;
  replySubject: string; setReplySubject: (s: string) => void;
  replyText: string; setReplyText: (s: string) => void;
  sending: boolean; onSend: () => void;
}) {
  if (!p.threads.length) {
    return (
      <Card title={p.scope === "company" ? "Переписка со всей компанией" : "Переписка"}>
        <Dialog items={p.fallback} />
        {p.replyOpenKey === "flat"
          ? <ReplyBox subject={p.replySubject} setSubject={p.setReplySubject}
                      text={p.replyText} setText={p.setReplyText}
                      sending={p.sending} onSend={p.onSend} onCancel={p.onCancel} />
          : <button className="btn btn-primary"
                    onClick={() => p.onOpenReply("flat", "")}>Ответить</button>}
      </Card>
    );
  }
  return (
    <>
      {p.threads.length > 1 && (
        <p className="muted small">
          С этой компанией {p.threads.length} отдельные переписки — они не связаны
          между собой в почте, поэтому показаны раздельно.
        </p>
      )}
      {p.threads.map((t) => (
        <Card key={t.key}
              title={t.subject || "(без темы)"}>
          <div className="muted small" style={{ marginBottom: 8 }}>
            {t.participants.join(", ")} · писем {t.n_out + t.n_in}
            {t.n_in ? ` · ответов ${t.n_in}` : " · ответов нет"}
          </div>
          <Dialog items={t.items} />
          {/* кнопка ответа ПОД последним письмом этой ветки */}
          {p.replyOpenKey === t.key
            ? <ReplyBox subject={p.replySubject} setSubject={p.setReplySubject}
                        text={p.replyText} setText={p.setReplyText}
                        sending={p.sending} onSend={p.onSend} onCancel={p.onCancel} />
            : <button className="btn btn-primary"
                      onClick={() => p.onOpenReply(t.key, t.subject)}>
                Ответить на это письмо
              </button>}
        </Card>
      ))}
    </>
  );
}

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
