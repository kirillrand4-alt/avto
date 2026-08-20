// Типизированный клиент API. Каждый метод бьёт в РЕАЛЬНЫЙ роут sender/api/app.py.
// Base "/api" (в dev проксируется Vite на serve-api :8080; в проде — обратный прокси).

import type { SendLimits, SendingWindow,
  Principal, LeadsResponse, LeadDetail, Lead, RecipientsResponse,
  Campaign, EventRow, SuppressionResponse, RatePoint, GateTrip,
  MailboxReadiness, CapacitySnapshot, DashboardResponse,
  CampaignDetail, User, AuditRow, DomainSummary, DnsReport, WarmupRow,
  Settings, SubjectView, ConfirmReview,
  MailboxBrief, MailFolder, MailMsg, MailFull, DialogItem, DialogThread,
  QuotaDay, QuotaRunState, QuotaView, ProverkaLegenda, SentMessage,
  ImportSvod,
} from "./types";

export const API_BASE = "/api";

/** Ошибка API с HTTP-статусом — экраны различают 401/403/404/409/400. */
export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(`API ${status}: ${detail}`);
    this.status = status;
    this.detail = detail;
  }
}

let tokenGetter: () => string | null = () => null;
/** Источник Bearer-токена (устанавливается AuthProvider). */
export function setTokenGetter(fn: () => string | null) {
  tokenGetter = fn;
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const token = tokenGetter();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(API_BASE + path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const detail = (data && (data.detail as string)) || res.statusText;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

function qs(params: Record<string, unknown>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const api = {
  // ---- auth ----
  login(username: string, password: string, totp_code?: string): Promise<{ token: string }> {
    return req("POST", "/auth/login", { username, password, totp_code });
  },
  logout(): Promise<{ ok: boolean }> {
    return req("POST", "/auth/logout", {});
  },
  me(): Promise<Principal> {
    return req("GET", "/me");
  },

  // ---- lead-desk (эпицентр) ----
  leads(f: {
    status?: string; assigned_to?: number; unassigned?: boolean;
    reply_kind?: string; napravlenie?: string;
    limit?: number; offset?: number;
  } = {}): Promise<LeadsResponse> {
    return req("GET", "/leads" + qs(f));
  },
  lead(id: number): Promise<LeadDetail> {
    return req("GET", `/leads/${id}`);
  },
  takeLead(id: number): Promise<{ lead: Lead }> {
    return req("POST", `/leads/${id}/take`, {});
  },
  setLeadStatus(id: number, status: string, note?: string): Promise<{ lead: Lead }> {
    return req("POST", `/leads/${id}/status`, { status, note });
  },
  assignLead(id: number, manager_id: number): Promise<{ lead: Lead }> {
    return req("POST", `/leads/${id}/assign`, { manager_id });
  },

  // ---- UI-ONLY обёртки ----
  recipients(f: Record<string, unknown> = {}): Promise<RecipientsResponse> {
    return req("GET", "/recipients" + qs(f));
  },
  campaigns(status?: string): Promise<{ campaigns: Campaign[] }> {
    return req("GET", "/campaigns" + qs({ status }));
  },
  events(f: { event_type?: string; campaign_id?: number; provider?: string; limit?: number; offset?: number } = {}): Promise<{ events: EventRow[] }> {
    return req("GET", "/events" + qs(f));
  },
  suppression(f: { scope?: string; reason?: string; limit?: number; offset?: number } = {}): Promise<SuppressionResponse> {
    return req("GET", "/suppression" + qs(f));
  },
  removeSuppression(sid: number, reason: string): Promise<{ ok: boolean }> {
    return req("DELETE", `/suppression/${sid}` + qs({ reason }));
  },
  /** Массовый запрет отправки по списку ИНН («идёт сделка» и т.п.) */
  suppressionBulkInn(text: string, reason?: string): Promise<{
    added: number; existed: number; invalid: string[]; total_parsed: number;
  }> {
    return req("POST", "/suppression/bulk-inn",
               { text, ...(reason ? { reason } : {}) });
  },
  dashboard(): Promise<DashboardResponse> {
    return req("GET", "/analytics/dashboard");
  },
  rates(f: { scope?: string; target?: string; days?: number } = {}): Promise<{ series: RatePoint[] }> {
    return req("GET", "/analytics/rates" + qs(f));
  },
  gatesActive(): Promise<{ trips: GateTrip[] }> {
    return req("GET", "/gates/active");
  },
  /** Ручной потолок дневной отправки: общий и по каждому ящику.
   *  Работает только вниз — выше рампы не поднять (Sender._daily_limit). */
  /** Пауза одного ящика. Причина обязательна — через неделю никто не вспомнит,
   *  почему он стоит. */
  pauseMailbox(mailboxId: string, paused: boolean, reason?: string):
    Promise<{ ok: boolean; mailbox_id: string; paused: boolean }> {
    return req("POST", `/mailboxes/${encodeURIComponent(mailboxId)}/pause`,
               { paused, reason });
  },
  /** ОСТАНОВИТЬ ВСЁ: при проблеме с репутацией счёт на минуты. */
  pauseAllMailboxes(paused: boolean, reason?: string):
    Promise<{ ok: boolean; paused: boolean }> {
    return req("POST", "/mailboxes/pause-all", { paused, reason });
  },
  sendLimits(): Promise<SendLimits> {
    return req("GET", "/send-limits");
  },
  setSendLimits(body: { all?: number | null; per_mailbox?: Record<string, number | null> }):
    Promise<SendLimits> {
    return req("POST", "/send-limits", body);
  },
  /** Тумблер автоответчика: выключает подготовку черновиков ответов сразу,
   *  без рестарта службы. */
  autoresponder(): Promise<{ enabled: boolean; available: boolean; note: string }> {
    return req("GET", "/autoresponder");
  },
  setAutoresponder(enabled: boolean): Promise<{ enabled: boolean; available: boolean; note: string }> {
    return req("POST", "/autoresponder", { enabled });
  },
  sendingWindow(): Promise<{ window: SendingWindow; source: string }> {
    return req("GET", "/sending-window");
  },
  setSendingWindow(w: SendingWindow): Promise<{ window: SendingWindow; source: string }> {
    return req("POST", "/sending-window", w);
  },
  allowOutOfBase(): Promise<{ allow_out_of_base: boolean; explicit: boolean }> {
    return req("GET", "/settings/out-of-base");
  },
  setAllowOutOfBase(allow: boolean): Promise<{ allow_out_of_base: boolean }> {
    return req("POST", "/settings/out-of-base", { allow });
  },
  // ---- дневная квота AI-генерации ----
  aiQuota(campaign_id: number, days = 7): Promise<QuotaView> {
    return req("GET", "/ai/quota" + qs({ campaign_id, days }));
  },
  /** schedule — ПАТЧ: только изменённые дни, 0 снимает квоту с дня. */
  setAiQuota(campaign_id: number, schedule: Record<string, number>):
    Promise<{ campaign_id: number; schedule: Record<string, number>; days: QuotaDay[] }> {
    return req("POST", "/ai/quota", { campaign_id, schedule });
  },
  runAiQuota(campaign_id: number): Promise<{ campaign_id: number; run: QuotaRunState }> {
    return req("POST", "/ai/quota/run", { campaign_id });
  },
  mailboxesReadiness(): Promise<{ mailboxes: MailboxReadiness[] }> {
    return req("GET", "/mailboxes/readiness");
  },
  capacity(): Promise<{ pools: CapacitySnapshot[] }> {
    return req("GET", "/capacity");
  },

  // ---- Фаза 2.1b ----
  createCampaign(name: string, segment?: string, opts?: { send_order?: string; min_priority_max?: number | null }): Promise<{ campaign_id: number }> {
    return req("POST", "/campaigns", {
      name, segment: segment?.trim() || null,
      send_order: opts?.send_order || null,
      min_priority_max: opts?.min_priority_max ?? null,
    });
  },
  campaignDetail(cid: number): Promise<CampaignDetail> {
    return req("GET", `/campaigns/${cid}`);
  },
  addStep(cid: number, step: { step_index: number; subject: string; body: string; delay_hours: number; gate: string }): Promise<{ step_id: number }> {
    return req("POST", `/campaigns/${cid}/steps`, step);
  },
  setCampaignStatus(cid: number, status: string): Promise<{ ok: boolean }> {
    return req("POST", `/campaigns/${cid}/status`, { status });
  },
  users(): Promise<{ users: User[] }> {
    return req("GET", "/users");
  },
  createUser(u: { username: string; password: string; role: string; enable_2fa?: boolean }): Promise<{ user_id: number; totp_uri?: string }> {
    return req("POST", "/users", u);
  },
  deactivateUser(uid: number): Promise<{ ok: boolean }> {
    return req("POST", `/users/${uid}/deactivate`, {});
  },
  activateUser(uid: number): Promise<{ ok: boolean }> {
    return req("POST", `/users/${uid}/activate`, {});
  },
  settings(): Promise<Settings> {
    return req("GET", "/settings");
  },
  audit(f: { action?: string; limit?: number; offset?: number } = {}): Promise<{ audit: AuditRow[] }> {
    return req("GET", "/audit" + qs(f));
  },
  domains(): Promise<{ domains: DomainSummary[] }> {
    return req("GET", "/domains");
  },
  domainDns(domain: string): Promise<{ dns: DnsReport }> {
    return req("GET", `/domains/${encodeURIComponent(domain)}/dns`);
  },
  warmup(): Promise<{ warmup: WarmupRow[] }> {
    return req("GET", "/warmup");
  },
  compliance(): Promise<{ suppression: Record<string, unknown> }> {
    return req("GET", "/compliance");
  },

  // ---- confirm-send: очередь подтверждений (Задачи 1/2/4) ----
  confirmQueue(f: { campaign_id?: number; limit?: number; gruppa?: string;
                    hide_blocked?: boolean } = {}): Promise<{
    pending: ConfirmReview[]; counts: Record<string, number>; live?: boolean;
    total?: number;
    /** сколько писем спрятано галкой и до какой даты (пока гейт был жив) */
    blocked_hidden?: number; blocked_until?: string;
    /** сколько писем идёт на СОБСТВЕННЫЕ почтовые серверы получателей */
    corp_total?: number;
    /** расшифровка значков проверок — приходит с сервера, чтобы список
     *  проверок не пришлось дублировать во фронте и рассинхронить */
    proverki_legenda?: ProverkaLegenda[];
  }> {
    return req("GET", "/confirm/queue" + qs(f));
  },
  /** Копия этого же письма на другой адрес: исходное остаётся на месте. */
  confirmKopiya(id: number, email: string): Promise<{
    ok: boolean; id: number; email: string; sozdano: boolean;
  }> {
    return req("POST", `/confirm/${id}/kopiya`, { email });
  },
  /** Письмо с нуля: ящик, адрес, тема, текст — сразу в очередь подтверждений. */
  confirmNovoe(body: { email: string; subject: string; body: string;
                       mailbox_id?: string; inn?: string;
                       campaign_id?: number }): Promise<{
    ok: boolean; id: number; email: string; mailbox_id?: string;
  }> {
    return req("POST", "/confirm/novoe", body);
  },
  // Группы получателей для фильтра очереди (новостные / металлообработка / …).
  // Считает сервер: `segment` получателя плюс список `extra_json.gruppy`.
  confirmGroups(): Promise<{ groups: { name: string; recipients: number }[] }> {
    return req("GET", "/confirm/groups");
  },
  confirmGet(id: number): Promise<ConfirmReview> {
    return req("GET", `/confirm/${id}`);
  },
  confirmDecision(id: number, body: {
    action: "approve" | "edit" | "skip" | "stoplist";
    subject?: string; body?: string; reason?: string;
    /** второе подтверждение оператора: письмо уходит вопреки заслонам */
    force?: boolean;
  }): Promise<{ ok: boolean; decided: boolean; review: ConfirmReview }> {
    return req("POST", `/confirm/${id}/decision`, body);
  },
  /** Ящик отправки, выбранный оператором (пишется в panel.mailbox_id — его же
   *  читает approve, так что выбор реально влияет на отправку). */
  confirmSetMailbox(id: number, mailbox_id: string): Promise<{ ok: boolean; review: ConfirmReview }> {
    return req("POST", `/confirm/${id}/mailbox`, { mailbox_id });
  },
  confirmSetRecipient(id: number, email: string): Promise<{ ok: boolean; review: ConfirmReview }> {
    return req("POST", `/confirm/${id}/recipient`, { email });
  },
  /** Вписать НОВЫЙ контакт этой компании и сразу выбрать его получателем.
   *  Отдельная ручка от confirmSetRecipient: та ходит только по контактам,
   *  уже известным карточке, а здесь адрес сначала проверяется (формат,
   *  стоп-лист, не закреплён ли за чужим ИНН) и заводится в базу под ИНН
   *  карточки. Кнопка была на сервере с 05.08 и пропала при пересборке
   *  фронта из репо-исходников, где её не оказалось. */
  confirmAddRecipient(id: number, email: string, note?: string): Promise<{
    ok: boolean; created_recipient?: boolean; review: ConfirmReview;
  }> {
    return req("POST", `/confirm/${id}/recipient/add`, { email, note });
  },
  confirmGolden(limit = 500): Promise<{ pairs: unknown[] }> {
    return req("GET", "/confirm/golden" + qs({ limit }));
  },
  /** Кнопка «в автоотправку»: первые N писем очереди → approved → цикл
   *  автоотправки шлёт их сам по времени получателя. Нажатие = решение
   *  владельца, поэтому включает и сам цикл. */
  confirmBulkToAuto(count: number, gruppa?: string): Promise<{
    moved: number;
    moved_items: { id: number; email: string; scheduled_at: string }[];
    skipped: { id: number; email: string; reason: string }[];
    auto_send: { enabled: boolean; running: boolean; live: boolean };
  }> {
    return req("POST", "/confirm/bulk-to-auto",
               { count, ...(gruppa ? { gruppa } : {}) });
  },
  autoSend(): Promise<{ enabled: boolean; running: boolean; live: boolean;
                        last?: Record<string, unknown> }> {
    return req("GET", "/auto-send");
  },
  autoSendSet(enabled: boolean): Promise<{ enabled: boolean; running: boolean;
                                           live: boolean }> {
    return req("POST", "/auto-send", { enabled });
  },
  subject(email: string): Promise<SubjectView> {
    return req("GET", `/subject/${encodeURIComponent(email)}`);
  },

  // ---- «Почта»: read-only IMAP-браузер + лента диалога ----
  mailMailboxes(): Promise<{ mailboxes: MailboxBrief[] }> {
    return req("GET", "/mail/mailboxes");
  },
  mailFolders(mb: string): Promise<{ folders: MailFolder[] }> {
    return req("GET", `/mail/${encodeURIComponent(mb)}/folders`);
  },
  mailMessages(mb: string, f: { folder?: string; limit?: number; offset?: number; search?: string } = {}): Promise<{ total: number; messages: MailMsg[] }> {
    return req("GET", `/mail/${encodeURIComponent(mb)}/messages` + qs(f));
  },
  mailMessage(mb: string, folder: string, uid: string): Promise<MailFull> {
    return req("GET", `/mail/${encodeURIComponent(mb)}/message` + qs({ folder, uid }));
  },
  mailThread(mb: string, folder: string, uid: string): Promise<{ thread: MailFull[] }> {
    return req("GET", `/mail/${encodeURIComponent(mb)}/thread` + qs({ folder, uid }));
  },
  /** Переписка по лиду: наши отправленные письма + ответы клиента.
   *  Ручка была, метода не было — карточка лида показывала журнал смены
   *  статусов вместо писем, и менеджер не мог прочитать ответ клиента. */
  importBazy(body: { text: string; name?: string; group?: string; dry_run: boolean }):
    Promise<ImportSvod> {
    return req("POST", "/recipients/zagruzka-partii", body);
  },
  otpravlennye(f: { q?: string; campaign_id?: number; mailbox_id?: string;
                    replied?: boolean; napravlenie?: string;
                    limit?: number; offset?: number }):
    Promise<{ vsego: number; pisma: SentMessage[] }> {
    return req("GET", "/messages/sent" + qs(f));
  },
  /** Одно письмо целиком. Поля именно такие, какие отдаёт store.message_full:
   *  текст лежит в `body`, а не в `body_rendered` — на этом 11.08 экран
   *  отправленных показывал «тела письма в базе нет» при живом тексте в базе. */
  pismoCelikom(id: number): Promise<{
    message_id: number; subject: string; body: string;
    body_source?: string; body_missing?: boolean;
    mailbox_id: string; status: string; sent_at: string | null;
    email: string; company: string; inn: string; contact_name?: string;
    thread_id?: string; campaign_id?: number | null;
  }> {
    return req("GET", `/messages/${id}`);
  },
  leadDialog(leadId: number): Promise<{
    thread: DialogItem[]; threads?: DialogThread[]; scope?: string }> {
    return req("GET", `/leads/${leadId}/dialog`);
  },
  /** #71: сгенерировать ещё N писем в очередь (сверх сделанных сегодня) */
  quotaRunCount(campaign_id: number, count: number):
      Promise<{ campaign_id: number; run: Record<string, unknown> }> {
    return req("POST", "/ai/quota/run", { campaign_id, count });
  },
  /** #71: перегенерировать одно письмо очереди */
  confirmRegenerate(id: number): Promise<{ ok: boolean; running: boolean }> {
    return req("POST", `/confirm/${id}/regenerate`);
  },
  confirmRegenerateStatus(id: number):
      Promise<{ running: boolean; known: boolean; error?: string | null; subject?: string }> {
    return req("GET", `/confirm/${id}/regenerate/status`);
  },
  /** #62: черновик ответа лида в очереди подтверждений (если есть) */
  leadReplyDraft(leadId: number): Promise<{ draft: { id: number; subject: string } | null }> {
    return req("GET", `/leads/${leadId}/reply-draft`);
  },
  /** #62: текст оператора -> черновик ответа в очередь подтверждений */
  // Загрузка вложения: multipart/form-data, а не JSON, поэтому мимо req<T> —
  // ему нужен Content-Type: application/json, а здесь границу формы ставит сам
  // браузер. Файл уезжает сразу при выборе, в ответ приходит расписка с id.
  async uploadVlozhenie(file: File): Promise<{ id: string; name: string; size: number }> {
    const форма = new FormData();
    форма.append("file", file);
    const headers: Record<string, string> = {};
    const token = tokenGetter();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const r = await fetch(`${API_BASE}/vlozheniya`, { method: "POST", headers, body: форма });
    if (!r.ok) {
      let detail = r.statusText;
      try { detail = (await r.json())?.detail || detail; } catch { /* тело не json */ }
      throw new ApiError(r.status, detail);
    }
    return r.json();
  },

  leadReply(leadId: number, body: { subject?: string; body: string;
                                    attachments?: string[] }):
      Promise<{ ok: boolean; review_id: number; created: boolean }> {
    return req("POST", `/leads/${leadId}/reply`, body);
  },
  contactDialog(recipientId: number): Promise<{ thread: DialogItem[] }> {
    return req("GET", `/dialog/${recipientId}`);
  },
  changePassword(old_password: string, new_password: string): Promise<{ ok: boolean }> {
    return req("POST", "/profile/password", { old_password, new_password });
  },

  // ---- P1.5.2: импорт базы из панели (CSV сырым телом, без multipart) ----
  async importRecipients(file: File, segment: string): Promise<{ import_id: string }> {
    const headers: Record<string, string> = { "Content-Type": "text/csv" };
    const token = tokenGetter();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(
      API_BASE + "/recipients/import" + qs({ segment: segment || undefined }),
      { method: "POST", headers, body: file },
    );
    const data = await res.json();
    if (!res.ok) throw new ApiError(res.status, (data && data.detail) || res.statusText);
    return data as { import_id: string };
  },
  importStatus(id: string): Promise<{ done: boolean; error: string | null; total_rows: number; imported: number; skipped_invalid: number }> {
    return req("GET", `/recipients/import/${id}`);
  },
};
