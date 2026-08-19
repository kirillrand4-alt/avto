// Экран 7 — Карточка лида. История переписки, действия: взять, сменить статус,
// нормализовать телефон, позвонить. Конкурентные действия ловят 409/400.

import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { useToast } from "../components/Toast";
import { Spinner, ErrorBox, StatusBadge, Card } from "../components/ui";
import { fmtDate, normalizePhone, replyBadge } from "../lib/format";
import { CompanyCard } from "./Confirm";
import type { DialogItem, DialogThread } from "../api/types";

// Ключи — те же, что понимает движок. Раньше здесь стояло not_qualified,
// которого движок не знал: кнопка отвечала «unknown lead status».
const NEXT_STATUS = [
  { key: "called", label: "Позвонил" },
  { key: "qualified", label: "Квалифицирован" },
  { key: "unqualified", label: "Не квалифицирован" },
  { key: "in_bitrix", label: "Передан в Bitrix" },
  { key: "not_interested", label: "Не интересно" },
  { key: "closed", label: "Закрыт" },
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
  // Вложения (владелец 19.08: «как в настоящей почте»). Файл уезжает на сервер
  // сразу при выборе — иначе оператор жмёт «в очередь», а письмо ждёт заливки
  // мегабайтов и выглядит зависшим. Здесь держим только расписку: id, имя, вес.
  const [files, setFiles] = useState<Array<{ id: string; name: string; size: number }>>([]);
  const [uploading, setUploading] = useState(false);
  const прикрепить = async (список: FileList | null) => {
    if (!список || список.length === 0) return;
    setUploading(true);
    try {
      for (const f of Array.from(список)) {
        const r = await api.uploadVlozhenie(f);
        setFiles((было) => было.concat([r]));
      }
    } catch (e) {
      toast("error", e instanceof ApiError ? e.detail : "Файл не загрузился");
    } finally {
      setUploading(false);
    }
  };
  const sendReply = useMutation({
    mutationFn: () => api.leadReply(leadId, {
      subject: replySubject || undefined, body: replyText,
      attachments: files.map((f) => f.id) }),
    onSuccess: (d) => {
      toast("success", `Черновик #${d.review_id} в очереди подтверждений`);
      setReplyOpen(null);
      setReplyText("");
      setFiles([]);
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
            files={files} uploading={uploading}
            onAttach={прикрепить}
            onDropFile={(id) => setFiles((б) => б.filter((x) => x.id !== id))}
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
      {/* ПОД перепиской, а не над ней (владелец 19.08): открывая лид,
          менеджер идёт читать ответ, а не реквизиты. Полная справка о
          компании — здесь, включая всех известных людей и телефоны СО
          ССЫЛКОЙ на страницу, откуда мы их взяли: «не понятно кому звонить»
          лечится не списком цифр, а возможностью проверить источник. */}
      <Kontakty k={q.data?.kontakty} />
      {/* Компания — та же карточка, что была у оператора при отправке
          письма (владелец 11.08). Правая колонка карточки лида пустовала,
          а собранное про компанию лежало рядом и не показывалось: менеджер
          звонил, ничего не зная про предприятие, которому мы писали. */}
      {q.data?.kartochka?.panel && (
        <>
          <CompanyCard p={q.data.kartochka.panel} />
          <p className="muted small">
            карточка на момент отправки
          {q.data.kartochka.tema ? ` · письмо «${q.data.kartochka.tema}»` : ""}
          {q.data.kartochka.otpravleno
              ? ` · ${fmtDate(q.data.kartochka.otpravleno)}` : ""}
          </p>
        </>
      )}
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
  files: Array<{ id: string; name: string; size: number }>;
  uploading: boolean;
  onAttach: (f: FileList | null) => void;
  onDropFile: (id: string) => void;
}) {
  return (
    <div className="reply-box">
      <input className="reply-subject" value={p.subject}
             placeholder="тема (Re: ...)"
             onChange={(e) => p.setSubject(e.target.value)} />
      <textarea className="reply-text" rows={8} value={p.text}
                placeholder="Текст ответа. Финал «С уважением,» допишется подписью отправки."
                onChange={(e) => p.setText(e.target.value)} />
      <div className="vlozheniya">
        <label className="btn btn-ghost">
          📎 Прикрепить файл
          <input type="file" multiple style={{ display: "none" }}
                 onChange={(e) => { p.onAttach(e.target.files); e.target.value = ""; }} />
        </label>
        {p.uploading && <span className="muted small">загружается…</span>}
        {p.files.map((f) => (
          <span key={f.id} className="vlozhenie" title={`${f.size} байт`}>
            {f.name} <span className="muted small">{(f.size / 1024).toFixed(0)} КБ</span>
            <button className="btn-link" title="убрать"
                    onClick={() => p.onDropFile(f.id)}>×</button>
          </span>
        ))}
      </div>
      <div className="actions">
        <button className="btn btn-primary"
                disabled={p.sending || p.uploading || !p.text.trim()}
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
  files: Array<{ id: string; name: string; size: number }>;
  uploading: boolean;
  onAttach: (f: FileList | null) => void;
  onDropFile: (id: string) => void;
}) {
  if (!p.threads.length) {
    return (
      <Card title={p.scope === "company" ? "Переписка со всей компанией" : "Переписка"}>
        <Dialog items={p.fallback} />
        {p.replyOpenKey === "flat"
          ? <ReplyBox subject={p.replySubject} setSubject={p.setReplySubject}
                      text={p.replyText} setText={p.setReplyText}
                      sending={p.sending} onSend={p.onSend} onCancel={p.onCancel}
                      files={p.files} uploading={p.uploading}
                      onAttach={p.onAttach} onDropFile={p.onDropFile} />
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
                        sending={p.sending} onSend={p.onSend} onCancel={p.onCancel}
                      files={p.files} uploading={p.uploading}
                      onAttach={p.onAttach} onDropFile={p.onDropFile} />
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

/** Полная справка о компании: люди, телефоны, почты — каждый со ссылкой на
 *  страницу-первоисточник. Владелец 19.08: «не понятно кому звонить». Пустые
 *  разделы не прячем молча, а говорим прямо: искали и не нашли — это разные
 *  вещи для того, кто собирается звонить. */
function Kontakty({ k }: { k?: {
  lyudi?: Array<{ person: string; post: string; role: string; phone: string;
                  email: string; source: string; source_url: string }>;
  telefony?: Array<{ phone: string; person: string; role: string;
                     source: string; source_url: string }>;
  pochty?: Array<{ email: string; role: string; person: string;
                   source: string; source_url: string; pometka: string }>;
  kompaniya?: Record<string, unknown>;
} | null }) {
  if (!k) return null;
  const люди = k.lyudi || [];
  const телефоны = k.telefony || [];
  const почты = k.pochty || [];
  const комп = (k.kompaniya || {}) as Record<string, string | number>;
  const ссылка = (url: string) => url
    ? <a href={url} target="_blank" rel="noreferrer" className="muted small"
         title={url}>источник</a>
    : <span className="muted small" title="страница-источник не сохранена">—</span>;
  return (
    <Card title="Компания: контакты и люди">
      {(comp_поле(комп, "name") || comp_поле(комп, "activity")) && (
        <dl className="kv">
          {comp_поле(комп, "name") && (<><dt>Название</dt><dd>{comp_поле(комп, "name")}</dd></>)}
          {comp_поле(комп, "activity") && (<><dt>Чем занимается</dt><dd>{comp_поле(комп, "activity")}</dd></>)}
          {comp_поле(комп, "okved") && (<><dt>ОКВЭД</dt><dd>{comp_поле(комп, "okved")}</dd></>)}
          {comp_поле(комп, "region") && (<><dt>Регион</dt><dd>{comp_поле(комп, "region")}</dd></>)}
          {comp_поле(комп, "address") && (<><dt>Адрес</dt><dd>{comp_поле(комп, "address")}</dd></>)}
          {comp_поле(комп, "director") && (<><dt>Директор по ЕГРЮЛ</dt><dd>{comp_поле(комп, "director")}</dd></>)}
          {comp_поле(комп, "site") && (
            <><dt>Сайт</dt><dd>
              <a href={String(comp_поле(комп, "site")).startsWith("http")
                        ? String(comp_поле(комп, "site"))
                        : `http://${comp_поле(комп, "site")}`}
                 target="_blank" rel="noreferrer">{comp_поле(комп, "site")}</a>
            </dd></>)}
        </dl>
      )}

      <h4>Люди {люди.length ? `(${люди.length})` : ""}</h4>
      {люди.length === 0
        ? <p className="muted small">Ни одного человека с должностью не нашли — звонить придётся на общий номер.</p>
        : (<table className="data-table"><tbody>
            {люди.map((л, i) => (
              <tr key={i}>
                <td><b>{л.person}</b>{л.post ? <div className="muted small">{л.post}</div> : null}</td>
                <td>{л.phone ? <a href={`tel:${л.phone}`}>{л.phone}</a> : ""}</td>
                <td>{л.email || ""}</td>
                <td>{л.role || ""}</td>
                <td>{ссылка(л.source_url)}</td>
              </tr>))}
          </tbody></table>)}

      <h4>Телефоны {телефоны.length ? `(${телефоны.length})` : ""}</h4>
      {телефоны.length === 0
        ? <p className="muted small">Телефонов не собрано.</p>
        : (<table className="data-table"><tbody>
            {телефоны.map((тел, i) => (
              <tr key={i}>
                <td><a href={`tel:${тел.phone}`}>{тел.phone}</a></td>
                <td>{тел.person || ""}</td>
                <td>{тел.role || ""}</td>
                <td>{ссылка(тел.source_url)}</td>
              </tr>))}
          </tbody></table>)}

      <h4>Почты {почты.length ? `(${почты.length})` : ""}</h4>
      {почты.length === 0
        ? <p className="muted small">Адресов не собрано.</p>
        : (<table className="data-table"><tbody>
            {почты.map((п, i) => (
              <tr key={i}>
                <td>{п.email}</td>
                <td>{п.role || ""}</td>
                <td>{п.person || ""}</td>
                <td>{п.pometka ? <span className="danger small">{п.pometka}</span> : ""}</td>
                <td>{ссылка(п.source_url)}</td>
              </tr>))}
          </tbody></table>)}
    </Card>
  );
}

function comp_поле(комп: Record<string, string | number>, ключ: string): string {
  const з = комп[ключ];
  return з === undefined || з === null || з === "" || з === 0 ? "" : String(з);
}
