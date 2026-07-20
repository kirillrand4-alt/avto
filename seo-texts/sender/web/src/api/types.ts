// Типы ответов API — ЗЕРКАЛО реальных сериализаторов sender/api/app.py.
// Не выдумывать поля: если поля нет в _*_json() бэкенда — его нет и здесь.

export type Role = "owner" | "manager";

export interface Principal {
  user_id: number;
  username: string;
  role: Role;
}

// _lead_json
export interface Lead {
  id: number;
  email: string;
  company_name: string | null;
  inn: string | null;
  status: string; // new|taken|called|qualified|not_qualified|in_bitrix|...
  reply_kind: string | null; // hot|interested|auto_reply|not_interested|unsub_request
  phone: string | null;
  need: string | null;
  assigned_to: number | null;
  bitrix_lead_id: number | null;
  version: number;
  sla_due_at: string | null;
  created_at: string | null;
}

export interface LeadsResponse {
  leads: Lead[];
  stats: Record<string, unknown>;
}

export interface LeadDetail {
  lead: Lead;
  history: unknown[];
}

// _recipient_json
export interface Recipient {
  id: number;
  email: string;
  domain: string;
  inn: string | null;
  company_name: string | null;
  segment: string | null;
  mx_provider: string | null;
  valid_status: string;
}

export interface RecipientsResponse {
  recipients: Recipient[];
  count: { total: number; by_status?: Record<string, number>; by_provider?: Record<string, number> };
}

// _campaign_json
export interface Campaign {
  id: number;
  name: string;
  status: string;
  legal_entity: string;
  created_at: string | null;
}

// _event_json
export interface EventRow {
  id: number;
  event_type: string;
  campaign_id: number | null;
  provider: string | null;
  mailbox_id: string | null;
  event_ts: string | null;
}

// _supp_json
export interface SuppressionRow {
  id: number;
  scope: string;
  value: string;
  reason: string;
  created_at: string | null;
  expires_at: string | null;
}

export interface SuppressionResponse {
  suppression: SuppressionRow[];
  stats: Record<string, unknown>;
}

// _rate_json
export interface RatePoint {
  target: string;
  sent: number;
  bounce: number;
  complaint: number;
  reply: number;
  bounce_rate: number;
  complaint_rate: number;
  reply_rate: number;
}

// _gate_json
export interface GateTrip {
  scope: string;
  target: string;
  metric: string;
  value: number;
  threshold: number;
  action: string;
}

// /mailboxes/readiness
export interface MailboxReadiness {
  mailbox_id: string;
  ready: boolean;
  ramp_day: number;
  daily_limit: number;
  sent_today: number;
  paused: boolean;
  reasons: string[];
}

// _capacity_json
export interface CapacitySnapshot {
  pool: string;
  mailbox_count: number;
  daily_capacity: number;
  sent_today: number;
  remaining_today: number;
  utilization_pct: number;
  paused_mailboxes: number;
}

// /analytics/dashboard — форма из analytics.dashboard()
export interface DashboardResponse {
  generated_at: string;
  since: string | null;
  global: {
    total_sent: number;
    total_bounced: number;
    total_complaints: number;
    global_bounce_rate: number;
    global_complaint_rate: number;
    active_mailboxes: number;
    paused_mailboxes: number;
  };
  mailboxes: unknown[];
  warmup: unknown[];
  campaigns: unknown[];
}
