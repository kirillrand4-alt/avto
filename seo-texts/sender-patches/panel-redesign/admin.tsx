// Оживлённые экраны Фазы 2.2b над эндпоинтами 2.1b: конструктор/детали кампании,
// домены (DNS-чек), прогрев, комплаенс+субъект ПД, настройки+команда, аудит.

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useToast } from "../components/Toast";
import { Spinner, ErrorBox, Empty, Card, StatusBadge } from "../components/ui";
import { fmtDate, pct } from "../lib/format";
import type { DnsReport } from "../api/types";

// ---- Экран 4: Конструктор кампании ----
export function CampaignNew() {
  const nav = useNavigate();
  const toast = useToast();
  const [name, setName] = useState("");
  const [segment, setSegment] = useState("");
  const [sendOrder, setSendOrder] = useState("");
  const [minPriority, setMinPriority] = useState("");
  const m = useMutation({
    mutationFn: () => api.createCampaign(name.trim(), segment, {
      send_order: sendOrder || undefined,
      min_priority_max: minPriority ? Number(minPriority) : null,
    }),
    onSuccess: (r) => { toast("success", "Кампания создана"); nav(`/campaigns/${r.campaign_id}`); },
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : "Ошибка"),
  });
  return (
    <div>
      <div className="page-head"><h1>Новая кампания</h1></div>
      <Card>
        <label className="field">Название
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Прогрев ритейл" />
        </label>
        <label className="field">Сегмент базы (таргетинг)
          <input value={segment} onChange={(e) => setSegment(e.target.value)}
                 placeholder="кц / meyer (пусто = вся база)" list="segment-hints" />
          <datalist id="segment-hints">
            <option value="кц" /><option value="meyer" />
          </datalist>
        </label>
        {!segment.trim() && (
          <p className="danger small">
            Без сегмента кампания уйдёт по ВСЕЙ базе (КЦ + Meyer вместе). Для
            раздельных рассылок укажите сегмент, каким он записан при импорте.
          </p>
        )}
        <label className="field">Порядок отправки (по PxR из базы обзвона)
          <select value={sendOrder} onChange={(e) => setSendOrder(e.target.value)}>
            <option value="">по id (как раньше)</option>
            <option value="pilot_asc">обкатка: малые PxR первыми</option>
            <option value="priority_desc">боевая: приоритетные первыми</option>
          </select>
        </label>
        <label className="field">Мин. балл по связке (1-5, пусто = без порога)
          <input type="number" min="1" max="5" value={minPriority}
                 onChange={(e) => setMinPriority(e.target.value)}
                 placeholder="напр. 4 — отсечь баллы 2-3" />
        </label>
        <p className="muted small">Юр-атрибуция (ООО+ИНН) подставится из конфига автоматически (ФЗ-38).</p>
        <button className="btn btn-primary" disabled={!name.trim() || m.isPending} onClick={() => m.mutate()}>
          Создать
        </button>
      </Card>
    </div>
  );
}

// ---- Экран 5: Детали кампании (шаги + воронка + статус) ----
export function CampaignDetail() {
  const { id } = useParams();
  const cid = Number(id);
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["campaign", cid], queryFn: () => api.campaignDetail(cid), enabled: Number.isFinite(cid) });
  const status = useMutation({
    mutationFn: (s: string) => api.setCampaignStatus(cid, s),
    onSuccess: () => { toast("success", "Статус обновлён"); qc.invalidateQueries({ queryKey: ["campaign", cid] }); },
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : "Ошибка"),
  });
  const [step, setStep] = useState({ subject: "", body: "" });
  const addStep = useMutation({
    mutationFn: () => api.addStep(cid, { step_index: (q.data?.steps.length ?? 0), subject: step.subject, body: step.body, delay_hours: (q.data?.steps.length ? 48 : 0), gate: "all" }),
    onSuccess: () => { toast("success", "Шаг добавлен"); setStep({ subject: "", body: "" }); qc.invalidateQueries({ queryKey: ["campaign", cid] }); },
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : "Ошибка"),
  });

  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  const { campaign, steps, funnel } = q.data!;
  return (
    <div>
      <div className="page-head">
        <h1>{campaign.name}</h1><StatusBadge status={campaign.status} kind="campaign" />
        <span className="muted small">
          {campaign.segment ? `сегмент: ${campaign.segment}` : "вся база (без сегмента)"}
        </span>
      </div>
      <Card title="Управление">
        <div className="actions">
          <button className="btn btn-primary" disabled={status.isPending || campaign.status === "active"}
                  onClick={() => status.mutate("active")}>Запустить</button>
          <button className="btn" disabled={status.isPending || campaign.status === "paused"}
                  onClick={() => status.mutate("paused")}>Пауза</button>
        </div>
      </Card>
      <GenerateCard cid={cid} hasSteps={(q.data?.steps.length ?? 0) > 0} />
      {funnel && (
        <Card title="Воронка">
          <div className="metrics">
            <M v={funnel.sent} l="Отправлено" /><M v={funnel.delivered} l="Доставлено" />
            <M v={`✉${funnel.opens ?? 0} (${pct(funnel.open_rate ?? 0)})`} l="Открыл*" />
            <M v={funnel.replies} l="Ответы" /><M v={pct(funnel.bounce_rate)} l="Bounce" />
            <M v={pct(funnel.complaint_rate)} l="Жалобы" /><M v={pct(funnel.reply_rate)} l="Reply-rate" />
          </div>
          <p className="muted small">
            * открытия в РФ приблизительны: Mail.ru и Яндекс проксируют картинки
            (недоучёт при выключенных картинках, накрутка антиспам-префетчем).
            Решения и гейты ведутся по ответам и кликам, не по открытиям.
          </p>
        </Card>
      )}
      <Card title={`Шаги цепочки (${steps.length})`}>
        {steps.length === 0 ? <p className="muted">Шагов нет.</p> : (
          <table className="data-table">
            <thead><tr><th>#</th><th>Тема</th><th>Задержка</th><th>Гейт</th><th>Юр-футер</th></tr></thead>
            <tbody>{steps.map((s) => (
              <tr key={s.id}><td>{s.step_index}</td><td>{s.subject_tmpl}</td>
                <td>{s.delay_hours} ч</td><td>{s.engagement_gate}</td><td>{s.include_legal ? "✓" : "—"}</td></tr>
            ))}</tbody>
          </table>
        )}
        <div className="add-step">
          <input placeholder="Тема письма ({company_name})" value={step.subject}
                 onChange={(e) => setStep({ ...step, subject: e.target.value })} />
          <textarea placeholder="Текст письма (merge-поля {company_name}, {inn})" value={step.body}
                    onChange={(e) => setStep({ ...step, body: e.target.value })} rows={3} />
          <button className="btn" disabled={!step.subject || !step.body || addStep.isPending}
                  onClick={() => addStep.mutate()}>Добавить шаг</button>
        </div>
      </Card>
    </div>
  );
}

// ---- Задача 1: пре-генерация писем на дневной лимит ----
function GenerateCard({ cid, hasSteps }: { cid: number; hasSteps: boolean }) {
  const toast = useToast();
  const [useAi, setUseAi] = useState(false);
  const [prog, setProg] = useState<null | { done: boolean; generated: number; failed: number; capacity: number; error: string | null; ai_generated?: number; flagged?: number; ai_fallback_merge?: number }>(null);
  const gen = useMutation({
    mutationFn: () => api.generateLetters(cid, useAi),
    onSuccess: async (r) => {
      if (r.status === "idle") { toast("error", r.reason || "Нет дневной ёмкости"); return; }
      toast("success", `Генерация запущена на ${r.capacity} писем${useAi ? " через fable + линзы" : ""}`);
      const gid = r.generate_id!;
      const poll = async () => {
        try {
          const s = await api.generateStatus(cid, gid);
          setProg(s);
          if (!s.done) setTimeout(poll, 2000);
          else toast("success", `Готово: ${s.generated} писем в очереди подтверждения`);
        } catch { /* игнор */ }
      };
      poll();
    },
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : "Ошибка"),
  });
  return (
    <Card title="Сгенерировать письма на очередь">
      <p className="muted small">На СЕГОДНЯШНИЙ лимит отправки (по ёмкости ящиков), топ-получатели
        по приоритету → в очередь подтверждения. Ты правишь/подтверждаешь каждое вручную.</p>
      <label className="check-row">
        <input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} />
        Генерировать через ИИ (fable, уникальный текст + прогон линз-ревьюеров). Без галочки — подстановка полей в шаблон.
      </label>
      <button className="btn btn-primary" disabled={!hasSteps || gen.isPending}
              onClick={() => gen.mutate()}>
        {gen.isPending ? "Запуск…" : useAi ? "Сгенерировать через ИИ" : "Собрать по шаблону"}
      </button>
      {!hasSteps && <p className="danger small">Добавьте хотя бы один шаг цепочки (это бриф для ИИ).</p>}
      {prog && (
        <p className="muted small">{prog.done ? "готово" : "генерация…"}: {prog.generated}/{prog.capacity}
          {prog.ai_generated ? ` · ИИ: ${prog.ai_generated}` : ""}
          {prog.flagged ? ` · с флагом линз: ${prog.flagged}` : ""}
          {prog.ai_fallback_merge ? ` · откат на шаблон: ${prog.ai_fallback_merge}` : ""}
          {prog.failed ? ` (ошибок: ${prog.failed})` : ""}{prog.error ? ` — ${prog.error}` : ""}</p>
      )}
    </Card>
  );
}

// ---- Экран 14: Домены (+DNS-чек) ----
export function Domains() {
  const q = useQuery({ queryKey: ["domains"], queryFn: () => api.domains() });
  const [dns, setDns] = useState<Record<string, DnsReport | "loading">>({});
  const toast = useToast();
  async function check(domain: string) {
    setDns((s) => ({ ...s, [domain]: "loading" }));
    try {
      const r = await api.domainDns(domain);
      setDns((s) => ({ ...s, [domain]: r.dns }));
    } catch (e) {
      toast("error", e instanceof ApiError ? e.detail : "DNS-чек не удался");
      setDns((s) => { const { [domain]: _, ...rest } = s; return rest; });
    }
  }
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  const rows = q.data!.domains;
  return (
    <div>
      <div className="page-head"><h1>Домены отправки</h1></div>
      {rows.length === 0 ? <Empty /> : (
        <table className="data-table">
          <thead><tr><th>Домен</th><th>Ящиков</th><th>Готовых</th><th>DKIM/SPF/DMARC</th><th></th></tr></thead>
          <tbody>{rows.map((d) => {
            const rep = dns[d.domain];
            return (
              <tr key={d.domain}>
                <td>{d.domain}</td><td>{d.mailboxes}</td>
                <td className={d.ready < d.mailboxes ? "danger" : ""}>{d.ready}/{d.mailboxes}</td>
                <td>{rep === "loading" ? "…" : rep ? <DnsCells r={rep} /> : "—"}</td>
                <td><button className="btn btn-ghost" onClick={() => check(d.domain)}>Проверить DNS</button></td>
              </tr>
            );
          })}</tbody>
        </table>
      )}
    </div>
  );
}
function DnsCells({ r }: { r: DnsReport }) {
  const mark = (v: boolean | null) => v === true ? "✓" : v === false ? "✗" : "?";
  return <span title={r.issues.join(", ")}>SPF {mark(r.spf)} · DKIM {mark(r.dkim)} · DMARC {mark(r.dmarc)}
    {r.dmarc_policy ? ` (p=${r.dmarc_policy})` : ""}</span>;
}

// ---- Экран 16: Прогрев ----
export function Warmup() {
  const q = useQuery({ queryKey: ["warmup"], queryFn: () => api.warmup() });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  const rows = q.data!.warmup;
  return (
    <div>
      <div className="page-head"><h1>Прогрев</h1></div>
      {rows.length === 0 ? <Empty hint="Прогрев не активирован (warmup.enabled_providers пуст в конфиге)" /> : (
        <table className="data-table">
          <thead><tr><th>Ящик</th><th>Фаза</th><th>Рамп-день</th><th>Цель/день</th><th>Отправлено</th><th>Репутация</th></tr></thead>
          <tbody>{rows.map((w) => (
            <tr key={w.mailbox_id}><td>{w.mailbox_id}</td><td>{w.phase}</td><td>{w.ramp_day}</td>
              <td>{w.warmup_target}</td><td>{w.warmup_sent_today}</td>
              <td>{w.reputation_score === null ? "—" : w.reputation_score.toFixed(2)}</td></tr>
          ))}</tbody>
        </table>
      )}
    </div>
  );
}

// ---- Экран 20: Комплаенс + субъект ПД ----
export function Compliance() {
  const q = useQuery({ queryKey: ["compliance"], queryFn: () => api.compliance() });
  const [email, setEmail] = useState("");
  const [subj, setSubj] = useState<null | Awaited<ReturnType<typeof api.subject>>>(null);
  const toast = useToast();
  async function lookup() {
    if (!email.trim()) return;
    try { setSubj(await api.subject(email.trim())); }
    catch (e) { toast("error", e instanceof ApiError ? e.detail : "Ошибка"); }
  }
  return (
    <div>
      <div className="page-head"><h1>Комплаенс (ФЗ-152)</h1></div>
      <Card title="Suppression — сводка">
        {q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} /> : (
          <pre className="json">{JSON.stringify(q.data!.suppression, null, 1)}</pre>
        )}
      </Card>
      <Card title="Субъект ПД (право на забвение / запрос РКН)">
        <div className="filterbar">
          <input placeholder="email субъекта" value={email} onChange={(e) => setEmail(e.target.value)} />
          <button className="btn" onClick={lookup}>Найти</button>
        </div>
        {subj && (
          <div>
            <p>Suppression: {subj.suppressed ? <span className="danger">да ({subj.suppression?.reason})</span> : "нет"}</p>
            <p className="muted small">История согласий/действий ({subj.consent_history.length}):</p>
            <pre className="json">{JSON.stringify(subj.consent_history, null, 1)}</pre>
            <p className="muted small">Просмотр записан в аудит.</p>
          </div>
        )}
      </Card>
    </div>
  );
}

function M({ v, l }: { v: unknown; l: string }) {
  return <div className="metric"><div className="metric-value">{String(v)}</div><div className="metric-label">{l}</div></div>;
}

// ---- Экран 23: Аудит ----
export function Audit() {
  const [action, setAction] = useState("");
  const q = useQuery({ queryKey: ["audit", action], queryFn: () => api.audit({ action: action || undefined, limit: 200 }) });
  const rows = q.data?.audit ?? [];
  return (
    <div>
      <div className="page-head"><h1>Аудит действий</h1></div>
      <div className="filterbar">
        <label>Действие
          <input placeholder="campaign.create / user.* / subject.view" value={action}
                 onChange={(e) => setAction(e.target.value)} />
        </label>
      </div>
      {q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} /> :
        rows.length === 0 ? <Empty /> : (
          <table className="data-table">
            <thead><tr><th>Время</th><th>Actor</th><th>Действие</th><th>Объект</th><th>Детали</th></tr></thead>
            <tbody>{rows.map((a) => (
              <tr key={a.id}><td>{fmtDate(a.created_at)}</td><td>{a.actor_user_id ?? "—"}</td>
                <td>{a.action}</td><td>{a.entity_type ?? ""} {a.entity_id ?? ""}</td>
                <td className="small">{JSON.stringify(a.detail)}</td></tr>
            ))}</tbody>
          </table>
        )}
    </div>
  );
}

// ---- Экран 21: Настройки + команда ----
export function Settings() {
  const qc = useQueryClient();
  const toast = useToast();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api.users() });
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.settings() });
  const [nu, setNu] = useState({ username: "", password: "", role: "manager" });
  const create = useMutation({
    mutationFn: () => api.createUser(nu),
    onSuccess: (r) => {
      toast("success", r.totp_uri ? "Создан (2FA URI показан в консоли)" : "Пользователь создан");
      setNu({ username: "", password: "", role: "manager" });
      qc.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : "Ошибка"),
  });
  const deact = useMutation({
    mutationFn: (uid: number) => api.deactivateUser(uid),
    onSuccess: () => { toast("success", "Деактивирован, сессии разорваны"); qc.invalidateQueries({ queryKey: ["users"] }); },
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : "Ошибка"),
  });
  const act = useMutation({
    mutationFn: (uid: number) => api.activateUser(uid),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["users"] }); },
  });
  return (
    <div>
      <div className="page-head"><h1>Настройки</h1></div>
      <Card title="Команда">
        {users.isLoading ? <Spinner /> : users.error ? <ErrorBox error={users.error} /> : (
          <table className="data-table">
            <thead><tr><th>#</th><th>Логин</th><th>Роль</th><th>2FA</th><th>Активен</th><th></th></tr></thead>
            <tbody>{users.data!.users.map((u) => (
              <tr key={u.id}><td>{u.id}</td><td>{u.username}</td><td>{u.role}</td>
                <td>{u.has_2fa ? "✓" : "—"}</td><td>{u.is_active ? "да" : <span className="danger">нет</span>}</td>
                <td>{u.is_active
                  ? <button className="btn btn-ghost danger" onClick={() => { if (confirm(`Деактивировать ${u.username}? Сессии разорвутся.`)) deact.mutate(u.id); }}>деактивировать</button>
                  : <button className="btn btn-ghost" onClick={() => act.mutate(u.id)}>активировать</button>}</td></tr>
            ))}</tbody>
          </table>
        )}
        <div className="add-step">
          <input placeholder="логин" value={nu.username} onChange={(e) => setNu({ ...nu, username: e.target.value })} />
          <input placeholder="пароль (8+)" type="password" value={nu.password} onChange={(e) => setNu({ ...nu, password: e.target.value })} />
          <select value={nu.role} onChange={(e) => setNu({ ...nu, role: e.target.value })}>
            <option value="manager">менеджер</option><option value="owner">владелец</option>
          </select>
          <button className="btn" disabled={!nu.username || nu.password.length < 8 || create.isPending}
                  onClick={() => create.mutate()}>Добавить</button>
        </div>
      </Card>
      <AutoresponderCard />
      <SendLimitsCard />
      <Card title="Конфигурация (read-only)">
        {settings.isLoading ? <Spinner /> : settings.error ? <ErrorBox error={settings.error} /> : (
          <div>
            <dl className="kv">
              <dt>Юрлицо</dt><dd>{settings.data!.legal.entity}, ИНН {settings.data!.legal.inn}</dd>
              <dt>Отписка</dt><dd>{settings.data!.legal.unsub_base_url}</dd>
            </dl>
            <p className="muted small">Пороги kill-switch:</p>
            <pre className="json">{JSON.stringify(settings.data!.gates, null, 1)}</pre>
            <p className="muted small">{settings.data!.readonly_note}</p>
          </div>
        )}
      </Card>
    </div>
  );
}

// ---- Дневной лимит отправки: общий для всех / индивидуально по ящику ----
function SendLimitsCard() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["send-limits"], queryFn: () => api.sendLimits() });
  const [all, setAll] = useState<string>("");
  const [per, setPer] = useState<Record<string, string>>({});
  // подхватываем текущие значения при загрузке
  const loaded = q.data;
  const allVal = all !== "" ? all : (loaded?.all != null ? String(loaded.all) : "");
  const save = useMutation({
    mutationFn: () => {
      const perNum: Record<string, number> = {};
      for (const [k, v] of Object.entries(per)) if (v !== "") perNum[k] = Number(v);
      return api.setSendLimits(allVal === "" ? null : Number(allVal), perNum);
    },
    onSuccess: () => { toast("success", "Лимиты сохранены"); qc.invalidateQueries({ queryKey: ["send-limits"] });
      qc.invalidateQueries({ queryKey: ["mailboxes-readiness"] }); },
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : "Ошибка"),
  });
  return (
    <Card title="Дневной лимит отправки">
      <p className="muted small">Сколько писем в день слать. «Общий» применяется к КАЖДОМУ ящику;
        индивидуальный лимит ящика важнее общего. Пусто = работает штатная кривая прогрева.</p>
      {q.isLoading ? <Spinner /> : q.error ? <ErrorBox error={q.error} /> : (
        <div>
          <div className="add-step">
            <label className="muted small">Общий на каждый ящик:&nbsp;
              <input type="number" min={0} style={{ width: 90 }} placeholder="прогрев"
                     value={allVal} onChange={(e) => setAll(e.target.value)} />
            </label>
          </div>
          <table className="data-table">
            <thead><tr><th>Ящик</th><th>Прогрев-день</th><th>Эффективный</th><th>Отправлено</th><th>Свой лимит</th></tr></thead>
            <tbody>{(loaded?.mailboxes ?? []).map((m) => (
              <tr key={m.mailbox_id}>
                <td>{m.mailbox_id}</td><td>{m.ramp_day}</td>
                <td>{m.effective_limit}</td><td>{m.sent_today}</td>
                <td><input type="number" min={0} style={{ width: 80 }}
                     placeholder={loaded?.per_mailbox?.[m.mailbox_id] != null ? String(loaded.per_mailbox[m.mailbox_id]) : "—"}
                     value={per[m.mailbox_id] ?? (loaded?.per_mailbox?.[m.mailbox_id] != null ? String(loaded.per_mailbox[m.mailbox_id]) : "")}
                     onChange={(e) => setPer({ ...per, [m.mailbox_id]: e.target.value })} /></td>
              </tr>
            ))}</tbody>
          </table>
          <button className="btn btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? "Сохранение…" : "Сохранить лимиты"}
          </button>
        </div>
      )}
    </Card>
  );
}

// ---- Задача 4: тумблер автоответчика (по умолчанию ВЫКЛ) ----
function AutoresponderCard() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["autoresponder"], queryFn: () => api.autoresponder() });
  const set = useMutation({
    mutationFn: (enabled: boolean) => api.setAutoresponder(enabled),
    onSuccess: (r) => { toast("success", r.enabled ? "Автоответчик ВКЛючён" : "Автоответчик выключен");
      qc.invalidateQueries({ queryKey: ["autoresponder"] }); },
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : "Ошибка"),
  });
  const enabled = q.data?.enabled ?? false;
  return (
    <Card title="Автоответчик на входящие">
      {q.isLoading ? <Spinner /> : (
        <div>
          <p>Статус: {enabled ? <span className="danger">ВКЛючён</span> : "выключен"}</p>
          <p className="muted small">По умолчанию ВЫКЛ. Включать только когда автоответы согласованы —
            до этого ответы пишутся вручную из карточки лида.</p>
          <button className="btn" disabled={set.isPending}
                  onClick={() => set.mutate(!enabled)}>
            {enabled ? "Выключить" : "Включить"}
          </button>
        </div>
      )}
    </Card>
  );
}
