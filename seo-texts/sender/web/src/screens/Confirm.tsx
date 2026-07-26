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

// Словари для оператора: в панель приходят технические значения движка
// (buying_power=small, budget=фрп, verified=inn), а продажнику нужен русский
// текст, по которому сразу понятно, звонить/писать или нет.
const POWER_RU: Record<string, string> = {
  micro: "микро — до 10 млн выручки",
  small: "небольшая — 10-100 млн",
  medium: "средняя — 100 млн - 1 млрд",
  large: "крупная — 1-5 млрд",
  enterprise: "очень крупная — свыше 5 млрд",
};
const BUDGET_RU: Record<string, string> = {
  "фрп": "есть льготный заём ФРП — деньги на модернизацию уже выделены",
  "оэз/тор": "резидент ОЭЗ/ТОР — льготы и инвестпрограмма",
};
const WINDOW_RU: Record<string, string> = {
  "0-30": "повод свежий, до 30 дней — закупку решают прямо сейчас",
  "31-90": "поводу 1-3 месяца — окно закупки ещё открыто",
};
// Из чего сложился балл — понятными словами, с подсказкой «что это значит»
const PART_RU: Array<{ key: "signal" | "revenue" | "verified" | "role";
                       label: string; max: number; hint: string }> = [
  { key: "signal", label: "новостной повод", max: 40,
    hint: "капвложение из новостей: чем свежее, тем больше баллов" },
  { key: "revenue", label: "выручка компании", max: 20,
    hint: "0 = выручки в базе нет, а не «компания бедная»" },
  { key: "verified", label: "данные проверены", max: 15,
    hint: "чем подтвердили, что сайт и контакты именно этой компании" },
  { key: "role", label: "должность контакта", max: 15,
    hint: "снабжение и главный инженер решают закупку; приёмная — нет" },
];

function ScoreHead({ p }: { p: ConfirmPanel }) {
  const s = p.scoring || {};
  if (!s.available) return <Card title="Оценка лида">нет данных (enrich недоступен)</Card>;
  const parts = s.parts || {};
  const score = s.score ?? 0;
  const color = s.color === "green" ? "#1a7f37" : s.color === "yellow" ? "#b58900" : "#6b7280";
  // Словами, а не цветом: оператор не обязан помнить, что 65 — это «зелёный»
  const verdict = score >= 65 ? "горячий — писать в первую очередь"
    : score >= 40 ? "тёплый — повод есть, но данные неполные"
    : "холодный — повода или данных мало";
  const power = POWER_RU[(s.buying_power || "").toLowerCase()] || s.buying_power || "";
  const budget = BUDGET_RU[(s.budget_confirmed || "").toLowerCase()] || s.budget_confirmed || "";
  const win = WINDOW_RU[s.capex_window || ""] || "";
  return (
    <Card title="Оценка лида">
      <div className="confirm-score-row">
        <div className="confirm-score-big" style={{ color }} title="сумма баллов из 90">
          {score}
        </div>
        <div>
          <div><b style={{ color }}>{verdict}</b></div>
          {win && <div className="muted">{s.capex_badge} — {win}</div>}
          {!win && <div className="muted">{s.capex_badge}</div>}
        </div>
      </div>
      {power && <div>масштаб закупок: <b>{power}</b></div>}
      {budget && <div>бюджет: <b>{budget}</b></div>}
      <table className="confirm-parts"><tbody>
        {PART_RU.map((it) => {
          const val = parts[it.key] || 0;
          return (
            <tr key={it.key} title={it.hint}>
              <td>{it.label}</td>
              <td><Bar val={val} max={it.max} /></td>
              <td>{val}/{it.max}</td>
            </tr>
          );
        })}
      </tbody></table>
      <div className="muted">наведите на строку — из чего складывается балл</div>
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
  // Панель может прийти неполной (письма ИИ-генерации какое-то время клались в
  // очередь с одним лишь ai-блоком). Раньше это был не «пустой блок», а падение
  // всего экрана: чтение c.lpr у undefined роняло React, и оператор видел белый
  // экран вместо очереди. Отсутствие данных показываем явно — решать вслепую
  // оператор не должен.
  if (!c) return <Card title="Контакт"><span className="confirm-red">нет данных контакта в карточке</span></Card>;
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
  if (!c) return <Card title="Компания"><span className="confirm-red">нет данных компании в карточке</span></Card>;
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
  // Оператор должен видеть ВЕСЬ текст, который уйдёт (требование владельца).
  // Подпись с юр-атрибуцией ФЗ-38 дописывается на отправке, в теле её нет —
  // раньше карточка обрывалась на «С уважением,», и было непонятно, чем
  // закончится письмо. Показываем её отдельным блоком, а не внутри
  // редактируемого тела: правится сырое тело, иначе подпись задвоится.
  const sig = letter.signature || "";
  return (
    <Card title={`Письмо: ${letter.subject || review.subject}`}>
      <pre className="confirm-letter">{highlight(letter.body || review.body)}</pre>
      {sig && (
        <pre className="confirm-letter confirm-letter-sig" data-testid="letter-signature">
          {sig}
        </pre>
      )}
      {sig && (
        <div className="muted">{letter.signature_note || "подпись добавляется при отправке"}</div>
      )}
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
  // Отдельно жёстко: комплаенс — это ФЗ-38, атрибуция и отписка. Пустой блок
  // здесь нельзя показать молча, иначе оператор подтвердит отправку, считая,
  // что проверок нет, тогда как их просто не посчитали.
  if (!c) {
    return (
      <Card title="Комплаенс ФЗ-38/152">
        <b className="confirm-red">🔴 проверки не выполнены — карточка пришла без блока комплаенса</b>
        <div className="muted">атрибуцию и отписку проверьте в тексте письма вручную</div>
      </Card>
    );
  }
  return (
    <Card title="Комплаенс ФЗ-38/152">
      <div>атрибуция ООО «Руспром»+ИНН/URL: {c.attribution_ok ? "✅" : <b className="confirm-red">🔴 НЕТ</b>}</div>
      <div>отписка в теле: {c.unsub_in_body ? "✅" : <b className="confirm-red">🔴 нет</b>}
        {c.unsub_note && <span className="muted"> — {c.unsub_note}</span>}</div>
      <div>персданные (ФИО): ×{c.fio_count} [шкала {c.fio_scale}]</div>
      {(c.banned_phrases || []).length > 0 && (
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

  // Оператор должен видеть И МОЧЬ СМЕНИТЬ отправителя и адресата: до этого
  // ящик подбирался молча внутри approve, а сменить адрес можно было только
  // через API. Обе ручки уже есть в движке — выносим их в карточку.
  const setMailbox = useMutation({
    mutationFn: (mailbox_id: string) => api.confirmSetMailbox(current!.id, mailbox_id),
    onSuccess: () => {
      toast("success", "Ящик отправки изменён");
      qc.invalidateQueries({ queryKey: ["confirm-queue"] });
    },
    onError: (err) => toast("error", `Ящик: ${(err as Error).message}`),
  });
  const setRecipient = useMutation({
    mutationFn: (email: string) => api.confirmSetRecipient(current!.id, email),
    onSuccess: (_d, email) => {
      toast("success", `Адрес получателя: ${email}`);
      qc.invalidateQueries({ queryKey: ["confirm-queue"] });
    },
    onError: (err) => {
      if (err instanceof ApiError) toast("error", `Адрес: ${err.detail}`);
      else toast("error", `Адрес: ${(err as Error).message}`);
    },
  });

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
            #{current.id} · ИНН {current.inn || "—"} · кампания {current.campaign_id ?? "—"}
          </div>

          <div className="confirm-routing">
            <label>
              с ящика:{" "}
              <select
                value={current.send_as?.mailbox_id || ""}
                disabled={setMailbox.isPending}
                onChange={(e) => setMailbox.mutate(e.target.value)}
              >
                {!current.send_as?.mailbox_id && <option value="">— не подобран —</option>}
                {(current.send_as?.options || []).map((o) => (
                  <option key={o.mailbox_id} value={o.mailbox_id} disabled={!o.available}>
                    {o.from_name || o.mailbox_id}{o.email ? ` <${o.email}>` : ""}
                    {o.division ? ` · ${o.division}` : ""}{o.available ? "" : " · недоступен"}
                  </option>
                ))}
              </select>{" "}
              <span className="muted">({current.send_as?.source || "подбор"})</span>
            </label>
            <label>
              кому:{" "}
              <select
                value={current.email}
                disabled={setRecipient.isPending}
                onChange={(e) => setRecipient.mutate(e.target.value)}
              >
                <option value={current.email}>{current.email}</option>
                {(panel.emails || [])
                  .filter((c) => c.email && c.email !== current.email)
                  .map((c) => (
                    <option key={c.email} value={c.email}>
                      {c.email}{c.role ? ` · ${c.role}` : ""}{c.person ? ` · ${c.person}` : ""}
                    </option>
                  ))}
              </select>
            </label>
            {current.send_as?.note && (
              <span className="confirm-red">{current.send_as.note}</span>
            )}
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
