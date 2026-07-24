// Типизированный клиент API. Каждый метод бьёт в РЕАЛЬНЫЙ роут sender/api/app.py.
// Base "/api" (в dev проксируется Vite на serve-api :8080; в проде — обратный прокси).

import type { SendingWindow,
  Principal, LeadsResponse, LeadDetail, Lead, RecipientsResponse,
  Campaign, EventRow, SuppressionResponse, RatePoint, GateTrip,
  MailboxReadiness, CapacitySnapshot, DashboardResponse,
  CampaignDetail, User, AuditRow, DomainSummary, DnsReport, WarmupRow,
  Settings, SubjectView, ConfirmReview,
  MailboxBrief, MailFolder, MailMsg, MailFull, DialogItem,
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
  sendingWindow(): Promise<{ window: SendingWindow; source: string }> {
    return req("GET", "/sending-window");
  },
  setSendingWindow(w: SendingWindow): Promise<{ window: SendingWindow; source: string }> {
    return req("POST", "/sending-window", w);
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

  // ---- confirm-send: очередь подтверждений (Задачи 1/2/4) ----
  confirmQueue(f: { campaign_id?: number; limit?: number } = {}): Promise<{
    pending: ConfirmReview[]; counts: Record<string, number>; live?: boolean;
  }> {
    return req("GET", "/confirm/queue" + qs(f));
  },
  confirmGet(id: number): Promise<ConfirmReview> {
    return req("GET", `/confirm/${id}`);
  },
  confirmDecision(id: number, body: {
    action: "approve" | "edit" | "skip" | "stoplist";
    subject?: string; body?: string; reason?: string;
  }): Promise<{ ok: boolean; decided: boolean; review: ConfirmReview }> {
    return req("POST", `/confirm/${id}/decision`, body);
  },
  confirmSetRecipient(id: number, email: string): Promise<{ ok: boolean; review: ConfirmReview }> {
    return req("POST", `/confirm/${id}/recipient`, { email });
  },
  confirmGolden(limit = 500): Promise<{ pairs: unknown[] }> {
    return req("GET", "/confirm/golden" + qs({ limit }));
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
