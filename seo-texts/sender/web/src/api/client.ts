// Типизированный клиент API. Каждый метод бьёт в РЕАЛЬНЫЙ роут sender/api/app.py.
// Base "/api" (в dev проксируется Vite на serve-api :8080; в проде — обратный прокси).

import type {
  Principal, LeadsResponse, LeadDetail, Lead, RecipientsResponse,
  Campaign, EventRow, SuppressionResponse, RatePoint, GateTrip,
  MailboxReadiness, CapacitySnapshot, DashboardResponse,
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
  mailboxesReadiness(): Promise<{ mailboxes: MailboxReadiness[] }> {
    return req("GET", "/mailboxes/readiness");
  },
  capacity(): Promise<{ pools: CapacitySnapshot[] }> {
    return req("GET", "/capacity");
  },
};
