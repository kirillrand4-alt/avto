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
  const m = useMutation({
    mutationFn: () => api.createCampaign(name.trim()),
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
      <div className="page-head"><h1>{campaign.name}</h1><StatusBadge status={campaign.status} kind="campaign" /></div>
      <Card title="Управление">
        <div className="actions">
          <button className="btn btn-primary" disabled={status.isPending || campaign.status === "active"}
                  onClick={() => status.mutate("active")}>Запустить</button>
          <button className="btn" disabled={status.isPending || campaign.status === "paused"}
                  onClick={() => status.mutate("paused")}>Пауза</button>
        </div>
      </Card>
      {funnel && (
        <Card title="Воронка">
          <div className="metrics">
            <M v={funnel.sent} l="Отправлено" /><M v={funnel.delivered} l="Доставлено" />
            <M v={funnel.replies} l="Ответы" /><M v={pct(funnel.bounce_rate)} l="Bounce" />
            <M v={pct(funnel.complaint_rate)} l="Жалобы" /><M v={pct(funnel.reply_rate)} l="Reply-rate" />
          </div>
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
