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
  // open-tracking: сколько раз «открыл» (справочно, в РФ приблизительно)
  opens?: number;
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
  // P1.6: баллы приоритета из базы обзвона
  priority_max?: number | null;
  pxr?: number | null;
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
  // таргетинг: сегмент базы (кц/meyer); null = вся база
  segment?: string | null;
  // P1.6: порядок отправки по PxR и порог балла
  send_order?: string | null;
  min_priority_max?: number | null;
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

// ---- Фаза 2.1b ----
export interface Step {
  id: number;
  step_index: number;
  delay_hours: number;
  subject_tmpl: string;
  engagement_gate: string;
  include_legal: boolean;
}
export interface Funnel {
  campaign_id: number;
  sent: number; delivered: number; bounced: number; complaints: number;
  replies: number; unsubscribes: number;
  bounce_rate: number; complaint_rate: number; reply_rate: number;
  // open-tracking: справочно, «в РФ приблизительно» (прокси картинок)
  opens: number; open_rate: number;
}
export interface CampaignDetail {
  campaign: Campaign;
  steps: Step[];
  funnel: Funnel | null;
}
export interface User {
  id: number; username: string; email: string | null; role: Role;
  is_active: boolean; has_2fa: boolean; created_at: string | null;
}
export interface AuditRow {
  id: number; actor_user_id: number | null; action: string;
  entity_type: string | null; entity_id: string | null;
  detail: Record<string, unknown>; ip: string | null; created_at: string;
}
export interface DomainSummary { domain: string; mailboxes: number; ready: number; }
export interface DnsReport {
  domain: string; spf: boolean | null; dkim: boolean | null; dmarc: boolean | null;
  mx_ok: boolean; spf_record: string | null; dmarc_policy: string | null;
  issues: string[];
}
export interface WarmupRow {
  mailbox_id: string; phase: string; ramp_day: number; warmup_target: number;
  warmup_sent_today: number; reputation_score: number | null;
}
export interface Settings {
  legal: { entity: string; inn: string; unsub_base_url: string };
  gates: Record<string, number | null>;
  readonly_note: string;
}
export interface SubjectView {
  email: string;
  consent_history: Array<Record<string, unknown>>;
  suppressed: boolean;
  suppression: SuppressionRow | null;
}

// ---- confirm-send (Задачи 1/2/4): панель — сырой JSON build_panel() ----
/** §3 BASE-MERGE: карточка новостного события (все, каждая со ссылкой). */
export interface NewsEvent {
  event_type: string; what: string; news_object: string; sum: string;
  hotness: number; date: string; source_name: string; source_url: string;
  match_ok: boolean; signal_match: string;
}

/** §3 BASE-MERGE: полная объединённая карточка компании (company_card). */
export interface CompanyFull {
  available: boolean;
  division?: string | null; division_source?: string | null;
  division_guess?: string | null;
  obzvon_available?: boolean; in_obzvon?: boolean;
  reg?: Record<string, string>;
  fin?: Record<string, string>;
  priority?: Record<string, string>;
  product?: Record<string, string>;
  contacts?: {
    emails: Array<{ email: string; role: string; person: string;
      mx_ok: boolean | null; source: string; source_url: string; origin: string }>;
    phones: Array<{ phone: string; source: string }>;
  };
  site_view?: { site: string; site_verified: string; cand_site: string; cand_site_note: string };
  activity?: string;
  opo?: { flag: string; object: string; source: string };
  zakupki?: { contact: string };
}

/** «Почта»: IMAP-браузер по ящикам панели (read-only). */
export interface MailboxBrief {
  mailbox_id: string; from_name: string; provider: string;
  division: string | null;
}
export interface MailFolder { name: string; role: string }
export interface MailMsg {
  uid: string; seen: boolean; from_name: string; from_addr: string;
  to_addr: string; subject: string; date: string; date_iso: string;
  message_id: string; in_reply_to: string; references: string[];
}
export interface MailFull extends MailMsg { body: string }
/** Лента диалога из БД (исходящие + входящие ответы). */
export interface DialogItem {
  direction: "out" | "in"; ts: string; kind: string; subject: string;
  body: string; mailbox_id: string; status?: string; reply_kind?: string;
}

/** Пометка «уже отправляли» (Фича 2) — батч из send_log. */
export interface SentFlag {
  ever: boolean; last_ts: string | null; replied: boolean; within_90d: boolean;
}

export interface ConfirmPanel {
  stop_flags: Array<{ code: string; label: string; severity: string }>;
  emails?: Array<{ email: string; role?: string; person?: string; mx_ok?: boolean | null; source?: string }>;
  news_events?: { count: number; events: NewsEvent[] };
  company_full?: CompanyFull;
  scoring: {
    available?: boolean; score?: number; color?: string;
    parts?: Record<string, number>; buying_power?: string;
    capex_badge?: string; budget_confirmed?: string;
  };
  signal: {
    present: boolean; label?: string;
    top?: { event_type: string; what: string; sum: string; date: string;
            hotness: number; stars: string; source_url: string };
    others?: Array<{ event_type: string; what: string }>;
  };
  contact: {
    email: string; role: string; router: boolean; person: string;
    lpr: string; mx_ok: boolean | null; verified: string;
    verified_icons: string; email_domain: string; site_domain: string;
    domain_mismatch: boolean; updated_at: string; source: string;
  };
  company: {
    inn: string; name: string; region: string; revenue_h: string;
    okved: string; director: string; activity: string; division: string;
    division_badge: string; why_equipment: string; site: string;
  };
  letter: { subject: string; body: string;
            highlights: Array<{ text: string; kind: string }> };
  kb: {
    cases: Array<{ id: string; city: string; what: string; brand: string }>;
    price_band: string; geo_fact: number | null; geo_fact_str: string;
    geo_claimed: number | null; geo_overclaim: boolean;
    trigger_phrase: string; trigger_confirmed: boolean | null;
  };
  compliance: {
    attribution_ok: boolean; unsub_in_body: boolean; unsub_note: string;
    fio_count: number; fio_scale: string; banned_phrases: string[];
  };
  history: {
    items: Array<Record<string, unknown>>;
    last: Record<string, unknown> | null;
    recent_90d: boolean; replied_before?: boolean; note?: string;
  };
  reserved: { catch_all: string };
  actions: { hotkeys: Record<string, string>; confirm_hold: boolean };
  kind?: string;
  incoming?: { from: string; snippet: string; classified: string; phone?: string | null };
  review?: { decision: string; escalate_reason?: string; qa_problems?: string[];
             verdicts?: Record<string, { verdict: string; problems: string[] }> };
  should: Record<string, unknown> & {
    deliverability?: { light: string; why: string };
    contact_age_days?: number | null; contact_age_flag?: string;
    price_gap?: boolean; legal_basis?: string;
    domain_concentration?: number | null;
  };
}

export interface ConfirmReview {
  id: number; dedup_key: string; campaign_id: number | null;
  recipient_id: number | null; message_id: number | null;
  inn: string | null; email: string; subject: string; body: string;
  status: string; reason: string | null;
  edited_subject: string | null; edited_body: string | null;
  diff_text: string | null; decided_by: string | null;
  decided_at: string | null; created_at: string; updated_at: string;
  kind?: string; in_reply_to?: string | null; thread_id?: string | null;
  sent?: SentFlag;
  panel: ConfirmPanel | Record<string, never>;
}

/** Окно авто-отправки (настраивается владельцем из панели). */
export interface SendingWindow {
  days: number[];   // ISO: 1=Пн .. 7=Вс
  start: string;    // "09:00"
  end: string;      // "11:00"
  tz?: string;      // "Europe/Moscow"
}
