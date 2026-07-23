// Типизированный клиент API. Каждый метод бьёт в РЕАЛЬНЫЙ роут sender/api/app.py.
// Base "/api" (в dev проксируется Vite на serve-api :8080; в проде — обратный прокси).

import type {
  Principal, LeadsResponse, LeadDetail, Lead, RecipientsResponse,
  Campaign, EventRow, SuppressionResponse, RatePoint, GateTrip,
  MailboxReadiness, CapacitySnapshot, DashboardResponse,
  CampaignDetail, User, AuditRow, DomainSummary, DnsReport, WarmupRow,
  Settings, SubjectView, ConfirmReview,
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
    reply_kind?: string; limit?: number; offset?: number;
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
  // Задача 3: ручной ответ по лиду (уходит тем же ящиком в тот же тред)
  replyLead(id: number, text: string, version: number, subject?: string): Promise<{
    ok: boolean; dry_run: boolean; sent_message_id: string | null;
    lead: Lead; history: unknown[];
  }> {
    return req("POST", `/leads/${id}/reply`, { text, version, subject });
  },

  // ---- UI-ONLY обёртки ----
  recipients(f: Record<string, unknown> = {}): Promise<RecipientsResponse> {
    return req("GET", "/recipients" + qs(f));
  },
  campaigns(status?: string): Promise<{ campaigns: Campaign[] }> {
    return req("GET", "/campaigns" + qs({ status }));
  },
  events(f: { event_type?: string; campaign_id?: number; provider?: string; limit?: number } = {}): Promise<{ events: EventRow[] }> {
    return req("GET", "/events" + qs(f));
  },
  suppression(f: { scope?: string; reason?: string; limit?: number } = {}): Promise<SuppressionResponse> {
    return req("GET", "/suppression" + qs(f));
  },
  removeSuppression(sid: number, reason: string): Promise<{ ok: boolean }> {
    return req("DELETE", `/suppression/${sid}` + qs({ reason }));
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
  audit(f: { action?: string; limit?: number } = {}): Promise<{ audit: AuditRow[] }> {
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

  // ---- Задача 2: добавить ящик из веба ----
  addMailbox(m: {
    mailbox_id: string; provider: string; smtp_host: string; smtp_port: number;
    imap_host: string; imap_port: number; login: string; password_env: string;
    from_name?: string; pool?: string; is_warmup_node?: boolean;
  }): Promise<{ ok: boolean; mailbox_id: string; note: string }> {
    return req("POST", "/mailboxes", m);
  },
  // ---- Задача 4: автоответчик ----
  autoresponder(): Promise<{ enabled: boolean }> {
    return req("GET", "/autoresponder");
  },
  setAutoresponder(enabled: boolean): Promise<{ ok: boolean; enabled: boolean }> {
    return req("POST", "/autoresponder", { enabled });
  },
  // ---- Задача 1: пре-генерация писем на дневной лимит (use_ai = через fable + линзы) ----
  generateLetters(cid: number, use_ai = false): Promise<{
    status: string; generate_id?: string; capacity: number; reason?: string; use_ai?: boolean;
  }> {
    return req("POST", `/campaigns/${cid}/generate`, { campaign_id: cid, use_ai });
  },
  generateStatus(cid: number, gid: string): Promise<{
    done: boolean; error: string | null; capacity: number;
    generated: number; failed: number; use_ai?: boolean;
    ai_generated?: number; flagged?: number; ai_fallback_merge?: number;
  }> {
    return req("GET", `/campaigns/${cid}/generate/${gid}`);
  },

  // ---- Дневной лимит отправки (все/один/каждый ящик) ----
  sendLimits(): Promise<{
    all: number | null; per_mailbox: Record<string, number>;
    mailboxes: { mailbox_id: string; ramp_day: number; effective_limit: number;
                 sent_today: number; override: number | null }[];
  }> {
    return req("GET", "/send-limits");
  },
  setSendLimits(all: number | null, per_mailbox: Record<string, number>): Promise<{
    ok: boolean; all: number | null; per_mailbox: Record<string, number>;
  }> {
    return req("POST", "/send-limits", { all, per_mailbox });
  },

  // ---- ручная отправка одного письма (owner, РЕАЛЬНАЯ отправка) ----
  sendManual(m: { to_email: string; subject: string; text: string; mailbox_id?: string }): Promise<{
    ok: boolean; dry_run: boolean; sent_message_id: string | null;
    mailbox_id: string; to_email: string;
  }> {
    return req("POST", "/send/manual", m);
  },

  // ---- confirm-send: очередь подтверждений (Задачи 1/2/4) ----
  confirmQueue(f: { campaign_id?: number; limit?: number } = {}): Promise<{
    pending: ConfirmReview[]; counts: Record<string, number>;
  }> {
    return req("GET", "/confirm/queue" + qs(f));
  },
  confirmGet(id: number): Promise<ConfirmReview> {
    return req("GET", `/confirm/${id}`);
  },
  confirmDecision(id: number, body: {
    action: "approve" | "edit" | "skip" | "stoplist" | "regenerate";
    subject?: string; body?: string; reason?: string; live?: boolean;
  }): Promise<{ ok: boolean; decided?: boolean; review?: ConfirmReview;
                regenerated?: boolean; generated?: boolean; new_review_id?: number | null;
                retired?: number; next?: ConfirmReview | null;
                sent?: { sent: boolean; dry_run?: boolean; error?: string; to_email?: string } | null }> {
    return req("POST", `/confirm/${id}/decision`, body);
  },
  confirmGolden(limit = 500): Promise<{ pairs: unknown[] }> {
    return req("GET", "/confirm/golden" + qs({ limit }));
  },
  subject(email: string): Promise<SubjectView> {
    return req("GET", `/subject/${encodeURIComponent(email)}`);
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
