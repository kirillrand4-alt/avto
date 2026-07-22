// Экран «Подтвердить отправку» (ENGINEER-TASKS-CONFIRM-SEND, Задачи 2/4).
// Рендерит ТОТ ЖЕ JSON build_panel(), что и CLI confirm-show — паритет.
// Порядок блоков по линзе UX: стоп-флаги -> скоринг -> повод -> контакт ->
// компания -> письмо -> KB -> комплаенс -> действия. Хоткеи: Enter/E/S/X.
// ⛔ Холд: «Отправить» лишь переводит письмо в очередь (scheduled) — SMTP нет.

import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import type { ConfirmPanel, ConfirmReview } from "../api/types";
import { useToast } from "../components/Toast";
import { Card, Empty, ErrorBox, Spinner } from "../components/ui";

const STOPLIST_REASONS = ["конкурент", "нерелевант", "плохие данные", "по запросу"];

function Bar({ val, max }: { val: number; max: number }) {
  const pct = max > 0 ? Math.round((100 * Math.min(val, max)) / max) : 0;
  return (
    <span className="confirm-bar" title={`${val}/${max}`}>
      <span className="confirm-bar-fill" style={{ width: `${pct}%` }} />
    </span>
  );
}

function ScoreHead({ p }: { p: ConfirmPanel }) {
  const s = p.scoring || {};
  if (!s.available) return <Card title="Скоринг">нет данных (enrich недоступен)</Card>;
  const parts = s.parts || {};
  const color = s.color === "green" ? "#1a7f37" : s.color === "yellow" ? "#b58900" : "#6b7280";
  return (
    <Card title="Скоринг">
      <div className="confirm-score-row">
        <div className="confirm-score-big" style={{ color }}>{s.score ?? 0}</div>
        <div>
          <div>{s.capex_badge}</div>
          <div className="muted">buying_power: <b>{s.buying_power || "—"}</b>
            {s.budget_confirmed ? <> · бюджет подтверждён: <b>{s.budget_confirmed}</b></> : null}</div>
        </div>
      </div>
      <table className="confirm-parts"><tbody>
        <tr><td>сигнал</td><td><Bar val={parts.signal || 0} max={40} /></td><td>{parts.signal || 0}/40</td></tr>
        <tr><td>выручка</td><td><Bar val={parts.revenue || 0} max={20} /></td><td>{parts.revenue || 0}/20</td></tr>
        <tr><td>verified</td><td><Bar val={parts.verified || 0} max={15} /></td><td>{parts.verified || 0}/15</td></tr>
        <tr><td>роль</td><td><Bar val={parts.role || 0} max={15} /></td><td>{parts.role || 0}/15</td></tr>
      </tbody></table>
    </Card>
  );
}

function SignalCard({ p }: { p: ConfirmPanel }) {
  const sig = p.signal || { present: false };
  if (!sig.present) return <Card title="Повод"><span className="muted">{sig.label || "повода нет — холодный заход"}</span></Card>;
  const t = sig.top!;
  return (
    <Card title="Новостной повод">
      <div><b>{t.event_type}</b> <span title={`hotness ${t.hotness}`}>{t.stars}</span> <span className="muted">{t.date}</span></div>
      <div>{t.what}{t.sum ? <b> · {t.sum}</b> : null}</div>
      {t.source_url && <a href={t.source_url} target="_blank" rel="noreferrer">источник ↗</a>}
      {(sig.others || []).length > 0 && (
        <details><summary>ещё сигналы ({sig.others!.length})</summary>
          {sig.others!.map((o, i) => <div key={i} className="muted">{o.event_type}: {o.what}</div>)}
        </details>
      )}
    </Card>
  );
}

function ContactCard({ p }: { p: ConfirmPanel }) {
  const c = p.contact;
  const lpr = { match: "✅ ЛПР совпал", mismatch: "⚠ ФИО разные", impersonal: "— безлично", no_data: "— нет данных ЛПР" }[c.lpr] || c.lpr;
  return (
    <Card title="Контакт">
      <div><b>{c.email}</b> {c.router && <span className="confirm-red">🔴 роутер</span>} <span className="muted">{c.role}</span></div>
      {c.person && <div>{c.person} <span className="muted">{lpr}</span></div>}
      {!c.person && <div className="muted">{lpr}</div>}
      <div>mx: {c.mx_ok === false ? <b className="confirm-red">❌ мёртв</b> : c.mx_ok ? "✅" : "не проверялся"}
        {" · "}verified: {c.verified_icons}</div>
      {c.domain_mismatch && (
        <div className="confirm-yellow">🟡 домен письма {c.email_domain} ≠ домен сайта {c.site_domain}</div>
      )}
    </Card>
  );
}

function CompanyCard({ p }: { p: ConfirmPanel }) {
  const c = p.company;
  const badge = c.division === "meyer"
    ? <span className="badge" style={{ background: "#7c3aed", color: "#fff" }}>Meyer</span>
    : c.division === "kc"
      ? <span className="badge" style={{ background: "#2563eb", color: "#fff" }}>КЦ</span>
      : <span className="badge">{c.division_badge}</span>;
  return (
    <Card title="Компания">
      <div>{badge} <b>{c.name || "—"}</b> <span className="muted">{c.region}</span></div>
      <div className="muted">выручка {c.revenue_h} · ОКВЭД {c.okved || "—"}{c.director ? ` · директор: ${c.director}` : ""}</div>
      {c.activity && <div>занимается: {c.activity}</div>}
      <div>зачем оборудование: <b>{c.why_equipment}</b></div>
    </Card>
  );
}

function LetterCard({ review, p }: { review: ConfirmReview; p: ConfirmPanel }) {
  const letter = p.letter || { subject: review.subject, body: review.body, highlights: [] };
  const marks = letter.highlights || [];
  // Подсветка простым split: помечаем вхождения текстов подстановок.
  function highlight(body: string) {
    if (!marks.length) return body;
    let parts: Array<string | JSX.Element> = [body];
    marks.forEach((m, mi) => {
      parts = parts.flatMap((seg) => {
        if (typeof seg !== "string" || !seg.includes(m.text)) return [seg];
        const out: Array<string | JSX.Element> = [];
        seg.split(m.text).forEach((chunk, i, arr) => {
          out.push(chunk);
          if (i < arr.length - 1)
            out.push(<mark key={`${mi}-${i}`} title={m.kind} className={`hl-${m.kind}`}>{m.text}</mark>);
        });
        return out;
      });
    });
    return parts;
  }
  return (
    <Card title={`Письмо: ${letter.subject || review.subject}`}>
      <pre className="confirm-letter">{highlight(letter.body || review.body)}</pre>
      {marks.length > 0 && (
        <div className="muted">подстановки: {marks.map((m) => `[${m.kind}] ${m.text}`).join("; ")}</div>
      )}
    </Card>
  );
}

function KbCard({ p }: { p: ConfirmPanel }) {
  const kb = p.kb || ({} as ConfirmPanel["kb"]);
  const empty = !(kb.cases?.length || kb.geo_fact_str || kb.trigger_phrase || kb.price_band);
  if (empty) return null;
  return (
    <Card title="KB-провенанс">
      {(kb.cases || []).map((c, i) => (
        <div key={i}>кейс {c.id || i + 1}: <b>{c.city}</b> — {c.what}</div>
      ))}
      {kb.price_band && <div>ценовой коридор: {kb.price_band}</div>}
      {kb.geo_fact_str && (
        <div>гео: {kb.geo_fact_str}
          {kb.geo_claimed != null && <> · в письме: {kb.geo_claimed}</>}
          {kb.geo_overclaim && <b className="confirm-yellow"> 🟡 ЗАВЫШЕНО</b>}
        </div>
      )}
      {kb.trigger_phrase && (
        <div className="muted">триггер: {kb.trigger_phrase} (подтверждено signals:{" "}
          {kb.trigger_confirmed == null ? "—" : kb.trigger_confirmed ? "да" : "нет"})</div>
      )}
    </Card>
  );
}

function ComplianceCard({ p }: { p: ConfirmPanel }) {
  const c = p.compliance;
  return (
    <Card title="Комплаенс ФЗ-38/152">
      <div>атрибуция ООО «Руспром»+ИНН/URL: {c.attribution_ok ? "✅" : <b className="confirm-red">🔴 НЕТ</b>}</div>
      <div>отписка в теле: {c.unsub_in_body ? "✅" : <b className="confirm-red">🔴 нет</b>}
        {c.unsub_note && <span className="muted"> — {c.unsub_note}</span>}</div>
      <div>персданные (ФИО): ×{c.fio_count} [шкала {c.fio_scale}]</div>
      {c.banned_phrases.length > 0 && (
        <div className="confirm-yellow">🟡 обороты: {c.banned_phrases.join(", ")}</div>
      )}
    </Card>
  );
}

function HistoryCard({ p }: { p: ConfirmPanel }) {
  const h = p.history || { items: [], last: null, recent_90d: false };
  return (
    <Card title="История контактов">
      {h.items.length === 0 ? (
        <span className="muted">контактов не было{h.note ? ` (${h.note})` : ""}</span>
      ) : (
        <>
          {h.recent_90d && <div className="confirm-red">🔴 контакт менее 90 дней назад!</div>}
          {h.items.slice(0, 5).map((it, i) => (
            <div key={i} className="muted">
              {String(it.ts || "").slice(0, 10)} · {String(it.outcome)} · {String(it.subject || "")}
            </div>
          ))}
          {h.replied_before && <div>✉ раньше отвечали</div>}
        </>
      )}
      <div className="muted">catch-all: {p.reserved?.catch_all}</div>
    </Card>
  );
}

function ShouldRow({ p }: { p: ConfirmPanel }) {
  const sh = p.should || {};
  const d = (sh.deliverability || {}) as { light?: string; why?: string };
  const light = d.light === "green" ? "🟢" : d.light === "yellow" ? "🟡" : d.light === "red" ? "🔴" : "";
  return (
    <div className="muted confirm-shouldrow">
      доставляемость {light} <span title={d.why}>({d.why})</span>
      {sh.contact_age_days != null && <> · возраст контакта {String(sh.contact_age_days)} дн [{String(sh.contact_age_flag)}]</>}
      {sh.price_gap ? <> · <span className="confirm-yellow">🟡 ценовой разрыв</span></> : null}
      {typeof sh.domain_concentration === "number" && sh.domain_concentration > 1 && (
        <> · домен в пачке ×{sh.domain_concentration}</>
      )}
      {" · "}основание: {String(sh.legal_basis || "—")}
    </div>
  );
}

export function Confirm() {
  const toast = useToast();
  const qc = useQueryClient();
  const [editMode, setEditMode] = useState(false);
  const [editSubject, setEditSubject] = useState("");
  const [editBody, setEditBody] = useState("");
  const [askReason, setAskReason] = useState<"skip" | "stoplist" | null>(null);
  const [reason, setReason] = useState("");

  const queue = useQuery({
    queryKey: ["confirm-queue"],
    queryFn: () => api.confirmQueue({ limit: 20 }),
  });
  const current: ConfirmReview | undefined = queue.data?.pending?.[0];
  const panel = (current?.panel || {}) as ConfirmPanel;
  const holdNeeded = Boolean(panel.actions?.confirm_hold);

  const decide = useMutation({
    mutationFn: (body: Parameters<typeof api.confirmDecision>[1]) =>
      api.confirmDecision(current!.id, body),
    onSuccess: (_d, vars) => {
      toast("success", `#${current!.id}: ${vars.action}`);
      setEditMode(false);
      setAskReason(null);
      setReason("");
      qc.invalidateQueries({ queryKey: ["confirm-queue"] });
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409) {
        toast("error", `Заслон: ${err.detail}`);
      } else {
        toast("error", `Ошибка: ${(err as Error).message}`);
      }
    },
  });

  const doApprove = useCallback(() => {
    if (!current || decide.isPending) return;
    if (holdNeeded && !window.confirm("Есть стоп-флаги! Отправить всё равно?")) return;
    decide.mutate({ action: "approve" });
  }, [current, decide, holdNeeded]);

  // Хоткеи (MUST 9): Enter/E/S/X. Не перехватываем, когда открыт ввод.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || editMode || askReason) return;
      if (!current) return;
      if (e.key === "Enter") { e.preventDefault(); doApprove(); }
      else if (e.key.toLowerCase() === "e" || e.key.toLowerCase() === "у") {
        setEditSubject(current.subject);
        setEditBody(current.body);
        setEditMode(true);
      } else if (e.key.toLowerCase() === "s" || e.key.toLowerCase() === "ы") {
        setAskReason("skip");
      } else if (e.key.toLowerCase() === "x" || e.key.toLowerCase() === "ч") {
        setAskReason("stoplist");
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, editMode, askReason, doApprove]);

  if (queue.isLoading) return <Spinner />;
  if (queue.error) return <ErrorBox error={queue.error} />;
  const counts = queue.data?.counts || {};

  return (
    <div className="confirm-screen">
      <div className="screen-head">
        <h1>Подтвердить отправку</h1>
        <div className="muted">
          в очереди: {counts.pending || 0} · одобрено: {counts.approved || 0} ·
          правок: {counts.edited || 0} · скипов: {counts.skipped || 0} ·
          стоп-лист: {counts.stoplist || 0}
        </div>
      </div>

      {!current && <Empty hint="Очередь подтверждений пуста — калибровать нечего." />}

      {current && (
        <>
          <div className="muted">
            #{current.id} · {current.email} · ИНН {current.inn || "—"} ·
            кампания {current.campaign_id ?? "—"}
          </div>

          {/* MUST 1: красная полоса стоп-флагов — ДО письма */}
          {(panel.stop_flags || []).length > 0 && (
            <div className="confirm-stopbar" data-testid="stop-flags">
              {panel.stop_flags.map((f, i) => (
                <div key={i}>⛔ {f.label}</div>
              ))}
              <div className="muted">«Отправить» потребует доп-подтверждения</div>
            </div>
          )}

          <div className="confirm-grid">
            <ScoreHead p={panel} />
            <SignalCard p={panel} />
            <ContactCard p={panel} />
            <CompanyCard p={panel} />
          </div>

          <LetterCard review={current} p={panel} />
          <KbCard p={panel} />
          <div className="confirm-grid">
            <ComplianceCard p={panel} />
            <HistoryCard p={panel} />
          </div>
          <ShouldRow p={panel} />

          {/* MUST 9: панель действий (фикс-низ) */}
          <div className="confirm-actions">
            {!editMode && !askReason && (
              <>
                <button className="btn btn-primary" disabled={decide.isPending} onClick={doApprove}>
                  [Enter] Отправить{holdNeeded ? " (стоп-флаги!)" : ""}
                </button>
                <button className="btn" onClick={() => { setEditSubject(current.subject); setEditBody(current.body); setEditMode(true); }}>
                  [E] Править
                </button>
                <button className="btn" onClick={() => setAskReason("skip")}>[S] Скип</button>
                <button className="btn btn-danger" onClick={() => setAskReason("stoplist")}>[X] Стоп-лист</button>
              </>
            )}
            {editMode && (
              <div className="confirm-edit">
                <input value={editSubject} onChange={(e) => setEditSubject(e.target.value)} placeholder="Тема" />
                <textarea rows={12} value={editBody} onChange={(e) => setEditBody(e.target.value)} />
                <div>
                  <button className="btn btn-primary" disabled={decide.isPending}
                          onClick={() => decide.mutate({ action: "edit", subject: editSubject, body: editBody })}>
                    Сохранить правку и отправить
                  </button>
                  <button className="btn btn-ghost" onClick={() => setEditMode(false)}>Отмена</button>
                  <span className="muted"> диф сохранится как золотая пара для калибровки промптов</span>
                </div>
              </div>
            )}
            {askReason && (
              <div className="confirm-reason">
                {askReason === "stoplist" ? (
                  <select value={reason} onChange={(e) => setReason(e.target.value)}>
                    <option value="">причина стоп-листа…</option>
                    {STOPLIST_REASONS.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                ) : (
                  <input value={reason} onChange={(e) => setReason(e.target.value)}
                         placeholder="причина скипа" autoFocus />
                )}
                <button className="btn btn-primary" disabled={decide.isPending || !reason}
                        onClick={() => decide.mutate({ action: askReason, reason })}>
                  Подтвердить
                </button>
                <button className="btn btn-ghost" onClick={() => { setAskReason(null); setReason(""); }}>Отмена</button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
