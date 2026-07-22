// Экран 7 — Карточка лида. История переписки, действия: взять, сменить статус,
// нормализовать телефон, позвонить. Конкурентные действия ловят 409/400.

import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { useToast } from "../components/Toast";
import { useAuth } from "../context/auth";
import { Spinner, ErrorBox, StatusBadge, Card } from "../components/ui";
import { fmtDate, normalizePhone, replyBadge } from "../lib/format";

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
  const { principal } = useAuth();
  const [replyText, setReplyText] = useState("");
  const [replySubject, setReplySubject] = useState("");

  const q = useQuery({
    queryKey: ["lead", leadId],
    queryFn: () => api.lead(leadId),
    enabled: Number.isFinite(leadId),
  });

  const reply = useMutation({
    mutationFn: () => api.replyLead(leadId, replyText.trim(), q.data!.lead.version,
                                   replySubject.trim() || undefined),
    onSuccess: (r) => {
      toast("success", r.dry_run ? "Ответ собран (холд — SMTP не вызван), записан в историю"
                                 : "Ответ отправлен");
      setReplyText(""); setReplySubject("");
      qc.invalidateQueries({ queryKey: ["lead", leadId] });
    },
    onError: (e) => toast("error", e instanceof ApiError
      ? (e.status === 409 ? e.detail : e.detail) : "Ошибка отправки"),
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

      <Card title="Ответить письмом">
        {lead.assigned_to == null ? (
          <p className="muted">Возьмите лид, чтобы ответить.</p>
        ) : (principal && principal.role !== "owner" && lead.assigned_to !== principal.user_id) ? (
          <p className="muted">Лид взят другим менеджером — отвечать может только он.</p>
        ) : (
          <div className="reply-box">
            <input className="reply-subject" placeholder="Тема (по умолчанию «Re: ваш запрос»)"
                   value={replySubject} onChange={(e) => setReplySubject(e.target.value)} />
            <textarea className="reply-text" rows={6} placeholder="Текст ответа. Байлайн «ООО «Руспром»» и футер отписки добавятся автоматически."
                      value={replyText} onChange={(e) => setReplyText(e.target.value)} />
            <div className="actions">
              <button className="btn btn-primary" disabled={!replyText.trim() || reply.isPending}
                      onClick={() => reply.mutate()}>
                {reply.isPending ? "Отправка…" : "Отправить ответ"}
              </button>
              <span className="muted small">Уходит тем же ящиком в тот же тред. Отписавшимся — заблокировано.</span>
            </div>
          </div>
        )}
      </Card>

      <Card title="История переписки">
        <History items={q.data!.history} />
      </Card>
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
