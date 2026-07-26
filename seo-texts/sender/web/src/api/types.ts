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
export interface ConfirmPanel {
  stop_flags: Array<{ code: string; label: string; severity: string }>;
  scoring: {
    available?: boolean; score?: number; color?: string;
    parts?: Record<string, number>; buying_power?: string;
    capex_badge?: string; budget_confirmed?: string;
    /** «0-30» | «31-90» | «» — окно капвложения, расшифровывается в карточке */
    capex_window?: string;
  };
  signal: {
    present: boolean; label?: string;
    top?: { event_type: string; what: string; sum: string; date: string;
            hotness: number; stars: string; source_url: string };
    others?: Array<{ event_type: string; what: string }>;
  };
  contact?: {
    email: string; role: string; router: boolean; person: string;
    lpr: string; mx_ok: boolean | null; verified: string;
    verified_icons: string; email_domain: string; site_domain: string;
    domain_mismatch: boolean; updated_at: string; source: string;
  };
  company?: {
    inn: string; name: string; region: string; revenue_h: string;
    /** число или null — «в базе нет данных» отличается от «нулевая выручка» */
    revenue?: number | null;
    okved: string; director: string; activity: string; division: string;
    division_badge: string; why_equipment: string; site: string;
    /** на чём основан вывод о направлении (ОКВЭД); деятельность — отдельно */
    why_basis?: string;
  };
  /** «reply» — это черновик ОТВЕТА клиенту (кладёт автоответчик) */
  kind?: string;
  /** письмо клиента, на которое отвечаем */
  incoming?: {
    from: string; snippet: string; classified: string; phone?: string | null;
  };
  /** решение и вердикты проверяющих линз по черновику ответа */
  review?: {
    decision?: string; escalate_reason?: string; qa_problems?: string[];
    verdicts?: Array<{ lens?: string; name?: string; ok?: boolean;
                       problems?: string[] }>;
  };
  /** выжимка новости, на которой писалось письмо (кладёт ИИ-генерация) */
  news_digest?: string;
  news_url?: string;
  /** все новости компании со ссылками и проверкой «про неё ли новость» */
  news_events?: {
    count: number;
    events: Array<{
      event_type: string; what: string; news_object?: string; sum: string;
      hotness: number; date: string; source_name: string; source_url: string;
      match_ok: boolean; signal_match: string;
    }>;
  };
  /** Полная карточка: регистрационные данные, отчётность, баллы базы обзвона
   *  и «Все категории оборудования» по ОКВЭД — то, чем обосновано направление. */
  company_full?: {
    available?: boolean; in_obzvon?: boolean;
    division_source?: string; activity?: string;
    /** коды ОКВЭД с названиями: в базе обзвона они лежат сжатыми, одними кодами */
    okved_decoded?: Array<{ code: string; name?: string }>;
    /** название основного кода — для компаний, у которых списка кодов нет */
    okved_main_name?: string;
    reg?: Record<string, string>;
    fin?: Record<string, string>;
    priority?: Record<string, string>;
    product?: Record<string, string>;
  };
  /** контакты компании плоским списком — для селекта «кому отправить» */
  emails?: Array<{
    email: string; role?: string; person?: string;
    mx_ok?: boolean | null; source?: string;
  }>;
  letter: {
    subject: string; body: string;
    highlights: Array<{ text: string; kind: string }>;
    /** подпись, дописываемая на отправке (в ней юр-атрибуция ФЗ-38) */
    signature?: string;
    /** тело + подпись: ровно то, что уйдёт адресату */
    final_body?: string;
    signature_note?: string;
  };
  kb: {
    cases: Array<{ id: string; city: string; what: string; brand: string }>;
    price_band: string; geo_fact: number | null; geo_fact_str: string;
    geo_claimed: number | null; geo_overclaim: boolean;
    trigger_phrase: string; trigger_confirmed: boolean | null;
  };
  compliance?: {
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
  panel: ConfirmPanel | Record<string, never>;
  /** «этому адресу/ИНН уже писали» — считается батчем на сервере, чтобы
   *  оператор видел риск повторного касания прямо в списке. */
  sent?: {
    ever: boolean; last_ts: string | null; replied: boolean;
    within_90d: boolean;
  };
  /** С какого ящика уйдёт письмо и какие ещё доступны. Считается на показ
   *  очереди: пауза/лимит/гейт ящика меняются в течение дня. */
  send_as?: {
    mailbox_id: string | null;
    from_name?: string;
    email?: string;
    /** «оператор» — выбран вручную, «подбор» — определил движок */
    source?: string;
    note?: string;
    options?: Array<{
      mailbox_id: string; from_name: string; email: string;
      division: string | null; available: boolean;
    }>;
  };
}

// ---------------------------------------------------------------------------
// Типы восстановлены 26.07.2026 по живому API (sender/api/app.py, ai_quota.py,
// mailbrowser.py, store.dialog_thread). Причина: исходники нового фронта в
// репозитории отсутствовали, бандл собран кем-то и залит как готовый dist.
// Сами .tsx удалось поднять из sourcemap боевого бандла, но типы при сборке
// стираются и в карту не попадают — эти интерфейсы написаны по фактическим
// формам ответов сервера, а не по памяти.
// ---------------------------------------------------------------------------

/** GET/POST /send-limits — ручной потолок дневной отправки. */
export interface SendLimits {
  /** общий потолок для всех ящиков (null = не задан) */
  all: number | null;
  /** потолок отдельных ящиков; важнее общего */
  per_mailbox: Record<string, number>;
  mailboxes: Array<{
    mailbox_id: string; from_name: string; division: string | null;
    ramp_day: number;
    /** сколько РЕАЛЬНО можно отправить сегодня: рампа, прижатая потолком */
    effective_limit: number;
    sent_today: number; paused: boolean;
    override: number | null;
  }>;
}

/** GET/POST /sending-window — окно, в которое разрешена отправка. */
export interface SendingWindow {
  /** дни недели 1-7 (пн-вс) */
  days: number[];
  /** «HH:MM» */
  start: string;
  /** «HH:MM» */
  end: string;
  tz: string;
}

/** Строка таблицы квоты ИИ-генерации: GET /ai/quota -> days[] (ai_quota.DayRow). */
export interface QuotaDay {
  /** «YYYY-MM-DD» */
  date: string;
  quota: number;
  generated: number;
  rejected: number;
  attempts: number;
  remaining: number;
  /** 1-7, пн-вс */
  weekday: number;
}

/** Итог одного прогона «сгенерировать сейчас» (ai_quota.RunResult). */
export interface QuotaRunResult {
  campaign_id: number;
  date: string;
  quota: number;
  before: number;
  planned: number;
  generated: number;
  rejected: number;
  candidates: number;
  /** пусто = работали; иначе почему ничего не сделали */
  reason: string;
  errors: string[];
}

/** Состояние фонового прогона (ai_quota.run_state). Ключи появляются по ходу. */
export interface QuotaRunState {
  running?: boolean;
  started_at?: string;
  /** прогон оборвался — служба перезапускалась посреди работы */
  stale?: boolean;
  error?: string;
  result?: QuotaRunResult;
}

/** GET /ai/quota целиком. */
export interface QuotaView {
  campaign_id: number;
  /** «YYYY-MM-DD» сервера — по нему UI подсвечивает строку «сегодня» */
  today: string;
  days: QuotaDay[];
  /** получателей в сегменте, у которых ещё нет письма */
  candidates_left: number;
  run: QuotaRunState;
}

/** GET /mail/mailboxes -> mailboxes[]. */
export interface MailboxBrief {
  mailbox_id: string;
  from_name: string;
  provider: string;
  division: string | null;
}

/** GET /mail/{id}/folders -> folders[]. */
export interface MailFolder {
  name: string;
  /** inbox | sent | spam | … (роль, если удалось определить) */
  role?: string;
}

/** Заголовки письма: GET /mail/{id}/messages -> messages[]. */
export interface MailMsg {
  uid: string;
  seen: boolean;
  from_name: string;
  from_addr: string;
  to_addr: string;
  subject: string;
  /** как прислал сервер, человекочитаемо */
  date: string;
  /** ISO, пусто если дату не удалось разобрать */
  date_iso: string;
  message_id: string;
  in_reply_to: string;
  references: string[];
}

/** Письмо с телом: GET /mail/{id}/message и элементы thread. */
export interface MailFull extends MailMsg {
  body: string;
}

/** Элемент переписки с получателем: GET /dialog/{recipient_id} -> thread[]. */
export interface DialogItem {
  direction: "out" | "in";
  /** время события/отправки */
  ts: string;
  /** sent | reply | reply_auto | complaint | dsn | bounce */
  kind: string;
  subject: string;
  body: string;
  mailbox_id: string;
  status?: string;
  message_id?: number | string;
  thread_id?: string;
  /** #64: адрес контакта — в ленте всей компании видно, с кем шёл разговор */
  email?: string;
}
