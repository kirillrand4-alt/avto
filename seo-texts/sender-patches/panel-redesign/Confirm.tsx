// Экран «Подтвердить отправку» (ENGINEER-TASKS-CONFIRM-SEND, Задачи 2/4).
// Рендерит ТОТ ЖЕ JSON build_panel(), что и CLI confirm-show — паритет.
// Порядок блоков по линзе UX: стоп-флаги -> скоринг -> повод -> контакт ->
// компания -> письмо -> KB -> комплаенс -> действия. Хоткеи: Ctrl+Enter/E/S/X.
//
// Редизайн (задача 47), что изменилось и ЗАЧЕМ:
//  1) ДВЕ КОЛОНКИ. Раньше экран показывал ровно одно письмо — первое в очереди,
//     и оператор не видел ни что за ним, ни сколько всего. Слева появился
//     список очереди со скроллом и постраничностью (25 писем на страницу,
//     `offset` у эндпоинта уже был), справа — карточка выбранного письма.
//     Виртуализация не нужна: в DOM всегда одна страница списка.
//  2) ФЛАГИ ПРИЧИН. Все стоп-флаги рисовались одной красной полосой, хотя у
//     них есть severity: red (блок) и yellow (предупреждение, например
//     «ИНН вне базы, но тумблер включён»). Теперь красные и жёлтые разведены,
//     и каждый флаг несёт значок + слово «стоп»/«внимание» + текст: понятно
//     без цвета (дальтонизм, удалёнка через ч/б RDP).
//  3) ПИСЬМО. Тело письма — колонка ~68 символов с увеличенным интерлиньяжем:
//     оператор его ЧИТАЕТ, а не сканирует, как таблицу.
//  4) ДЕЙСТВИЯ. Панель действий отделена от опасных кнопок промежутком, чтобы
//     «Стоп-лист» не стоял вплотную к «Отправить».
// Логика решений, мутации и хоткеи не тронуты.

import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import type { ConfirmPanel, ConfirmReview } from "../api/types";
import { useToast } from "../components/Toast";
import {
  Card, DivisionBadge, Empty, ErrorBox, FlagList, Icon, Kbd, Pager, Spinner,
} from "../components/ui";

const STOPLIST_REASONS = ["конкурент", "нерелевант", "плохие данные", "по запросу"];

/** Размер страницы очереди. 25 строк держат DOM лёгким и влезают в один экран
 *  списка без «бесконечной ленты», в которой оператор теряет место. */
const PAGE = 25;

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
  if (!s.available) return <Card title="Скоринг"><span className="muted">нет данных (enrich недоступен)</span></Card>;
  const parts = s.parts || {};
  const color = s.color === "green" ? "var(--ok)" : s.color === "yellow" ? "var(--warn)" : "var(--muted)";
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
        <details><summary className="muted small">ещё сигналы ({sig.others!.length})</summary>
          {sig.others!.map((o, i) => <div key={i} className="muted">{o.event_type}: {o.what}</div>)}
        </details>
      )}
    </Card>
  );
}

function NewsEventsCard({ p }: { p: ConfirmPanel }) {
  // §3 BASE-MERGE: ВСЕ новостные события, каждое с кликабельным источником;
  // самый горячий раскрыт, остальные под катом.
  const ne = p.news_events;
  if (!ne || !ne.count) return null;
  const [top, ...rest] = ne.events;
  const row = (ev: (typeof ne.events)[number], i: number) => (
    <div key={i} style={{ marginBottom: "var(--sp-2)" }}>
      <div>
        {ev.match_ok
          ? <span className="pill pill-ok" title="имя компании найдено в тексте">
              <Icon name="ok" width={12} height={12} /> имя найдено
            </span>
          : <span className="pill pill-warn" title="имени компании в тексте нет — проверь руками">
              <Icon name="warn" width={12} height={12} /> {ev.signal_match || "имени нет в тексте"}
            </span>}{" "}
        <b>{ev.event_type}</b> <span className="muted">{ev.date}</span>
        {ev.sum ? <b> · {ev.sum}</b> : null}
      </div>
      <div>{ev.what || ev.news_object}</div>
      {ev.source_url && (
        <a href={ev.source_url} target="_blank" rel="noreferrer">
          {ev.source_name || "источник"} ↗
        </a>
      )}
    </div>
  );
  return (
    <Card title={`Новостные события (${ne.count})`}>
      {row(top, 0)}
      {rest.length > 0 && (
        <details><summary className="muted small">остальные события ({rest.length})</summary>
          {rest.map((ev, i) => row(ev, i + 1))}
        </details>
      )}
    </Card>
  );
}

function CompanyFullCard({ p }: { p: ConfirmPanel }) {
  // §3 BASE-MERGE: «вся информация» — раскрывающийся блок полной карточки.
  const cf = p.company_full;
  if (!cf || !cf.available) return null;
  const reg = cf.reg || {};
  const contacts = cf.contacts || { emails: [], phones: [] };
  const prod = cf.product || {};
  const sv = cf.site_view;
  return (
    <details className="card">
      <summary>
        Полная карточка компании · направление:{" "}
        <b>{cf.division || "НЕ ОПРЕДЕЛЕНО"}</b> (база обзвона)
        {cf.division_guess ? ` · предположение enrich: ${cf.division_guess}` : ""}
      </summary>
      {reg.name_short && (
        <div style={{ marginTop: "var(--sp-3)" }}>
          <b>{reg.name_short}</b> <span className="muted">{reg.status}</span>
          <div className="muted">{reg.address}</div>
          <div className="muted">ОКВЭД {reg.okved_main}{reg.okved_all_codes ? ` · все: ${reg.okved_all_codes}` : ""}</div>
          {reg.director && <div>директор: {reg.director}</div>}
        </div>
      )}
      {prod.equip_categories && (
        <div style={{ marginTop: "var(--sp-3)" }}>
          продукт: <b>{prod.equip_categories}</b>
          {cf.priority?.priority_max ? ` (балл ${cf.priority.priority_max})` : ""}
          {prod.calc_comment && <div className="muted">{prod.calc_comment}</div>}
        </div>
      )}
      {contacts.emails.length > 0 && (
        <div style={{ marginTop: "var(--sp-3)" }}>
          {contacts.emails.map((e, i) => (
            <div key={i}>
              <Icon name="mail" width={12} height={12} /> <b>{e.email}</b> <span className="muted">{e.role}</span>{" "}
              <span className="badge">{e.origin === "enrich" ? "сайт" : "база"}</span>{" "}
              {e.source_url && <a href={e.source_url} target="_blank" rel="noreferrer">страница ↗</a>}
            </div>
          ))}
        </div>
      )}
      {contacts.phones.length > 0 && (
        <div style={{ marginTop: "var(--sp-3)" }}>
          {contacts.phones.map((ph, i) => (
            <div key={i}>тел. {ph.phone} <span className="muted">[{ph.source}]</span></div>
          ))}
        </div>
      )}
      {sv && (sv.site || sv.cand_site) && (
        <div style={{ marginTop: "var(--sp-3)" }}>
          {sv.site
            ? <>сайт: <b>{sv.site}</b> <span className="muted">(verified: {sv.site_verified})</span></>
            : <>сайт-кандидат: {sv.cand_site} <span className="confirm-yellow">({sv.cand_site_note})</span></>}
        </div>
      )}
      {cf.opo && (cf.opo.object || cf.opo.flag) && (
        <div style={{ marginTop: "var(--sp-3)" }}>
          ОПО: <b>{cf.opo.object || cf.opo.flag}</b>{" "}
          {cf.opo.source && (cf.opo.source.startsWith("http")
            ? <a href={cf.opo.source} target="_blank" rel="noreferrer">источник ↗</a>
            : <span className="muted">{cf.opo.source}</span>)}
        </div>
      )}
      {cf.zakupki?.contact && (
        <div style={{ marginTop: "var(--sp-3)" }}>закупки: {cf.zakupki.contact}</div>
      )}
    </details>
  );
}

function ContactCard({ p }: { p: ConfirmPanel }) {
  const c = p.contact;
  if (!c) return null; // B1: без инфо-панели карточка просто не рисуется, экран жив
  const lpr = { match: "ЛПР совпал", mismatch: "ФИО разные", impersonal: "безлично", no_data: "нет данных ЛПР" }[c.lpr] || c.lpr;
  return (
    <Card title="Контакт">
      <div>
        <b>{c.email}</b>{" "}
        {c.router && <span className="pill pill-danger"><Icon name="warn" width={12} height={12} /> роутер</span>}{" "}
        <span className="muted">{c.role}</span>
      </div>
      {c.person && <div>{c.person} <span className="muted">{lpr}</span></div>}
      {!c.person && <div className="muted">{lpr}</div>}
      <div>
        mx: {c.mx_ok === false
          ? <b className="confirm-red">мёртв</b>
          : c.mx_ok ? <span className="confirm-ok">отвечает</span> : <span className="muted">не проверялся</span>}
        {" · "}verified: {c.verified_icons}
      </div>
      {c.domain_mismatch && (
        <div className="confirm-yellow">
          <Icon name="warn" width={12} height={12} /> домен письма {c.email_domain} ≠ домен сайта {c.site_domain}
        </div>
      )}
    </Card>
  );
}

function CompanyCard({ p }: { p: ConfirmPanel }) {
  const c = p.company;
  if (!c) return null; // B1
  return (
    <Card title="Компания">
      <div><DivisionBadge division={c.division} fallback={c.division_badge} /> <b>{c.name || "—"}</b> <span className="muted">{c.region}</span></div>
      <div className="muted">выручка {c.revenue_h} · ОКВЭД {c.okved || "—"}{c.director ? ` · директор: ${c.director}` : ""}</div>
      {c.activity && <div>занимается: {c.activity}</div>}
      <div>зачем оборудование: <b>{c.why_equipment}</b></div>
    </Card>
  );
}

// Подписи к подсветке подстановок: оператор должен понимать, что за цветное
// пятно в тексте, не наводя мышь.
const HL_LABELS: Record<string, string> = {
  name: "имя", city: "город", price: "цена", trigger: "триггер",
  case: "кейс", company: "компания",
};

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
  const kinds = Array.from(new Set(marks.map((m) => m.kind)));
  return (
    <Card title="Письмо">
      <div className="letter-subject">{letter.subject || review.subject}</div>
      <pre className="confirm-letter">{highlight(letter.body || review.body)}</pre>
      {kinds.length > 0 && (
        <div className="letter-legend">
          подсветка подстановок:
          {kinds.map((k) => (
            <span key={k}>
              <span className={`sw hl-${k}`} /> {HL_LABELS[k] || k}
            </span>
          ))}
        </div>
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
          {kb.geo_overclaim && <b className="confirm-yellow"> ЗАВЫШЕНО</b>}
        </div>
      )}
      {kb.trigger_phrase && (
        <div className="muted">триггер: {kb.trigger_phrase} (подтверждено signals:{" "}
          {kb.trigger_confirmed == null ? "—" : kb.trigger_confirmed ? "да" : "нет"})</div>
      )}
    </Card>
  );
}

/** Строка комплаенса: галка или явный красный «НЕТ» со значком. */
function CheckRow({ ok, label, note }: { ok: boolean; label: string; note?: string }) {
  return (
    <div className={ok ? "" : "confirm-red"}>
      <Icon name={ok ? "ok" : "stop"} width={13} height={13} /> {label}: <b>{ok ? "есть" : "НЕТ"}</b>
      {note && <span className="muted"> — {note}</span>}
    </div>
  );
}

function ComplianceCard({ p }: { p: ConfirmPanel }) {
  const c = p.compliance;
  if (!c) return null; // B1
  return (
    <Card title="Комплаенс ФЗ-38/152">
      <CheckRow ok={c.attribution_ok} label="атрибуция ООО «Руспром» + ИНН/URL" />
      <CheckRow ok={c.unsub_in_body} label="отписка в теле" note={c.unsub_note} />
      <div>персданные (ФИО): ×{c.fio_count} [шкала {c.fio_scale}]</div>
      {(c.banned_phrases || []).length > 0 && (
        <div className="confirm-yellow">
          <Icon name="warn" width={12} height={12} /> обороты: {c.banned_phrases.join(", ")}
        </div>
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
          {h.recent_90d && (
            <div className="confirm-red">
              <Icon name="stop" width={13} height={13} /> контакт менее 90 дней назад
            </div>
          )}
          {h.items.slice(0, 5).map((it, i) => (
            <div key={i} className="muted">
              {String(it.ts || "").slice(0, 10)} · {String(it.outcome)} · {String(it.subject || "")}
            </div>
          ))}
          {h.replied_before && <div>раньше отвечали</div>}
        </>
      )}
      <div className="muted">catch-all: {p.reserved?.catch_all}</div>
    </Card>
  );
}

function ReplyView({ review, p }: { review: ConfirmReview; p: ConfirmPanel }) {
  // Панель ОТВЕТА клиенту: входящее письмо + классификация + черновик + вердикт.
  const inc = p.incoming || { from: review.email, snippet: "", classified: "" };
  const rev = p.review || { decision: "" };
  return (
    <>
      <Card title={`Входящее от ${inc.from}`}>
        <div className="muted">класс: <b>{inc.classified || "—"}</b>
          {inc.phone ? <> · телефон: {inc.phone}</> : null}</div>
        <pre className="confirm-letter">{inc.snippet || "(текст входящего недоступен)"}</pre>
      </Card>
      <Card title="Черновик ответа">
        <div className="muted">ревью: <b>{rev.decision || "—"}</b>
          {rev.escalate_reason ? <span className="confirm-yellow"> · {rev.escalate_reason}</span> : null}</div>
        {(rev.qa_problems || []).length > 0 && (
          <div className="confirm-yellow">QA: {(rev.qa_problems || []).join("; ")}</div>
        )}
        <pre className="confirm-letter">{review.body}</pre>
      </Card>
    </>
  );
}

function ShouldRow({ p }: { p: ConfirmPanel }) {
  const sh = p.should || {};
  const d = (sh.deliverability || {}) as { light?: string; why?: string };
  const dot = d.light === "green" ? "green" : d.light === "yellow" ? "yellow" : d.light === "red" ? "red" : "";
  return (
    <div className="confirm-shouldrow">
      <span>доставляемость <span className={`qi-dot ${dot}`} style={{ display: "inline-block", verticalAlign: "middle" }} />
        <span title={d.why}> ({d.why})</span></span>
      {sh.contact_age_days != null && <span>· возраст контакта {String(sh.contact_age_days)} дн [{String(sh.contact_age_flag)}]</span>}
      {sh.price_gap ? <span className="confirm-yellow">· ценовой разрыв</span> : null}
      {typeof sh.domain_concentration === "number" && sh.domain_concentration > 1 && (
        <span>· домен в пачке ×{sh.domain_concentration}</span>
      )}
      <span>· основание: {String(sh.legal_basis || "—")}</span>
    </div>
  );
}

/** Строка очереди слева: балл, адрес, компания, метки флагов. */
function QueueItem({ r, active, onPick }: { r: ConfirmReview; active: boolean; onPick: () => void }) {
  const p = (r.panel || {}) as ConfirmPanel;
  const flags = p.stop_flags || [];
  const hasStop = flags.some((f) => (f.severity || "red") !== "yellow");
  const hasWarn = flags.some((f) => f.severity === "yellow");
  const color = p.scoring?.color === "green" ? "green" : p.scoring?.color === "yellow" ? "yellow" : "";
  const company = p.company?.name || r.inn || "";
  return (
    <button type="button" onClick={onPick}
            className={`confirm-queue-item${active ? " current" : ""}`}
            aria-current={active ? "true" : undefined}>
      <div className="qi-top">
        <span className={`qi-dot ${hasStop ? "red" : color}`}
              title={hasStop ? "есть стоп-флаги" : `скоринг: ${p.scoring?.score ?? "нет данных"}`} />
        <span className="qi-email">{r.email}</span>
        {hasStop && <span className="qi-flag" title="стоп-флаги">СТОП</span>}
        {!hasStop && hasWarn && <span className="qi-flag warn" title="предупреждение">ВНИМ</span>}
      </div>
      <div className="qi-sub">
        {r.kind === "reply" ? "ответ · " : ""}{company || r.subject}
      </div>
    </button>
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
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const queue = useQuery({
    queryKey: ["confirm-queue", offset],
    queryFn: () => api.confirmQueue({ limit: PAGE, offset }),
  });
  const pending: ConfirmReview[] = queue.data?.pending ?? [];
  // Выбор — производная величина: если выбранное письмо ушло из очереди
  // (одобрено/скипнуто), молча берём первое на странице. Отдельного эффекта
  // синхронизации не нужно, а значит нет и «мигания» на решении.
  const current: ConfirmReview | undefined =
    pending.find((r) => r.id === selectedId) ?? pending[0];
  const panel = (current?.panel || {}) as ConfirmPanel;
  const holdNeeded = Boolean(panel.actions?.confirm_hold);
  // §4 точка 2: несовпадение/пустое направление = кнопка ЗАБЛОКИРОВАНА
  // (не «доп-подтверждение»); бэкенд всё равно откажет (ConfirmBlockedError).
  const divisionBlocked = (panel.stop_flags || []).some(
    (f) => (f.code || "").startsWith("division"));

  // Последняя страница опустела после решений: отступаем назад, иначе оператор
  // смотрит в пустой экран при непустой очереди.
  useEffect(() => {
    if (!queue.isFetching && pending.length === 0 && offset > 0) {
      setOffset((o) => Math.max(0, o - PAGE));
    }
  }, [queue.isFetching, pending.length, offset]);

  const setRecipient = useMutation({
    mutationFn: (email: string) => api.confirmSetRecipient(current!.id, email),
    onSuccess: (d) => {
      toast("success", `Адрес отправки: ${d.review.email}`);
      qc.invalidateQueries({ queryKey: ["confirm-queue"] });
    },
    onError: (err) => {
      toast("error", err instanceof ApiError ? err.detail : "не удалось сменить адрес");
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
      setSelectedId(null);
      qc.invalidateQueries({ queryKey: ["confirm-queue"] });
      // счётчик в боковом меню обязан гаснуть вместе с очередью
      qc.invalidateQueries({ queryKey: ["confirm-counts-nav"] });
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

  // Переход по очереди с клавиатуры: стрелки двигают выбор внутри страницы.
  const move = useCallback((delta: number) => {
    if (!current || pending.length === 0) return;
    const i = pending.findIndex((r) => r.id === current.id);
    const next = pending[Math.min(pending.length - 1, Math.max(0, i + delta))];
    if (next) setSelectedId(next.id);
  }, [current, pending]);

  // Хоткеи (MUST 9): Ctrl+Enter/E/S/X. Не перехватываем, когда открыт ввод.
  // A1-A3: одиночный Enter отправку НЕ вызывает (случайный Enter в live-режиме
  // шёл бы реальным письмом); только Ctrl/Cmd+Enter и без автоповтора клавиши.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement;
      const tag = el?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" ||
          el?.isContentEditable || editMode || askReason) return;
      if (!current) return;
      if (e.key === "Enter") {
        if (!(e.ctrlKey || e.metaKey) || e.repeat) return; // просто Enter — игнор
        e.preventDefault(); doApprove();
      }
      else if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
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
  }, [current, editMode, askReason, doApprove, move]);

  if (queue.isLoading) return <Spinner label="Загружаем очередь подтверждений…" />;
  if (queue.error) return <ErrorBox error={queue.error} onRetry={() => queue.refetch()} />;
  const counts = queue.data?.counts || {};
  const live = Boolean(queue.data?.live);
  const isReply = current?.kind === "reply";
  const sendLabel = live ? "Отправить сейчас (вживую)" : "В очередь на отправку";
  const totalPending = counts.pending ?? undefined;

  return (
    <div className="confirm-screen">
      <div className="screen-head">
        <h1>Подтвердить отправку</h1>
        <div className="confirm-counts">
          <span className="pill pill-brand">в очереди: {counts.pending || 0}</span>
          <span className="pill pill-ok">одобрено: {counts.approved || 0}</span>
          <span className="pill">правок: {counts.edited || 0}</span>
          <span className="pill">скипов: {counts.skipped || 0}</span>
          <span className="pill pill-danger">стоп-лист: {counts.stoplist || 0}</span>
        </div>
        <div className="spacer" />
        {live
          ? <span className="confirm-mode-live" title="Одобрение отправляет письмо немедленно">живая отправка</span>
          : <span className="confirm-mode-queue">режим очереди</span>}
      </div>

      {!current && !queue.isFetching && (
        <Empty title="Очередь пуста"
               hint="Писем на подтверждении нет. Сгенерируйте партию на экране «Кампании» (карточка дневной квоты)." />
      )}

      {current && (
        <div className="confirm-layout">
          {/* ---- левая колонка: очередь постранично ---- */}
          <aside className="confirm-queue" aria-label="Очередь писем">
            <div className="confirm-queue-head">
              <Icon name="inbox" />
              <span className="grow">страница из {pending.length}</span>
              {queue.isFetching && <span className="spinner-inline" title="обновляем" />}
            </div>
            <div className="confirm-queue-list">
              {pending.map((r) => (
                <QueueItem key={r.id} r={r} active={r.id === current.id}
                           onPick={() => setSelectedId(r.id)} />
              ))}
            </div>
            <Pager offset={offset} shown={pending.length} total={totalPending}
                   unit="писем"
                   onPrev={() => { setSelectedId(null); setOffset(Math.max(0, offset - PAGE)); }}
                   onNext={() => { setSelectedId(null); setOffset(offset + PAGE); }} />
          </aside>

          {/* ---- правая колонка: карточка письма ---- */}
          <div className="confirm-main">
            <div className="confirm-head">
              <span className="confirm-head-id">#{current.id}</span>
              <span className="badge">{isReply ? "ОТВЕТ клиенту" : "исходящее"}</span>
              <b>{current.email}</b>
              <span className="muted">ИНН {current.inn || "—"}</span>
              {current.sent?.ever && (
                <span className={`pill ${current.sent.within_90d ? "pill-danger" : "pill-warn"}`}
                      title={`последняя отправка ${current.sent.last_ts?.slice(0, 10) || "?"}${current.sent.replied ? ", был ответ" : ""}`}>
                  <Icon name="mail" width={12} height={12} />
                  Отправляли{current.sent.last_ts ? ` (${current.sent.last_ts.slice(0, 10)})` : ""}
                  {current.sent.within_90d ? " · менее 90 дней" : ""}
                  {current.sent.replied ? " · был ответ" : ""}
                </span>
              )}
              {/* Фича 1: сменить email отправки на другой контакт компании */}
              {!isReply && (panel.emails || []).length > 1 && (
                <label className="row" style={{ marginLeft: "auto" }}>
                  <span className="muted small">Адрес отправки</span>
                  <select value={current.email}
                          disabled={setRecipient.isPending}
                          onChange={(e) => setRecipient.mutate(e.target.value)}>
                    {(panel.emails || []).map((em) => (
                      <option key={em.email} value={em.email}>
                        {em.email}{em.role ? ` · ${em.role}` : ""}{em.mx_ok === false ? " · MX не отвечает" : ""}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>

            {/* MUST 1: флаги причин — ДО письма, красные и жёлтые раздельно */}
            <FlagList flags={panel.stop_flags || []}
                      note={divisionBlocked
                        ? "Гейт направлений: отправка заблокирована, кнопка недоступна."
                        : (panel.stop_flags || []).length > 0
                          ? "«Отправить» потребует доп-подтверждения."
                          : undefined} />

            {isReply ? (
              <ReplyView review={current} p={panel} />
            ) : (
              <>
                <div className="confirm-grid">
                  <ScoreHead p={panel} />
                  <SignalCard p={panel} />
                  <ContactCard p={panel} />
                  <CompanyCard p={panel} />
                </div>
                <NewsEventsCard p={panel} />
                <CompanyFullCard p={panel} />
                <LetterCard review={current} p={panel} />
                <KbCard p={panel} />
                <div className="confirm-grid">
                  <ComplianceCard p={panel} />
                  <HistoryCard p={panel} />
                </div>
                <ShouldRow p={panel} />
              </>
            )}

            {/* MUST 9: панель действий (липкая у низа окна) */}
            <div className="confirm-actions">
              {!editMode && !askReason && (
                <>
                  <button className="btn btn-primary"
                          disabled={decide.isPending || divisionBlocked}
                          title={divisionBlocked ? "гейт направлений: отправка заблокирована" : undefined}
                          onClick={doApprove}>
                    {divisionBlocked
                      ? "Заблокировано (направления)"
                      : <><Kbd>Ctrl+Enter</Kbd> {sendLabel}{holdNeeded ? " (стоп-флаги!)" : ""}</>}
                  </button>
                  <button className="btn" disabled={divisionBlocked}
                          onClick={() => { setEditSubject(current.subject); setEditBody(current.body); setEditMode(true); }}>
                    <Kbd>E</Kbd> Править
                  </button>
                  <span className="sep" />
                  <button className="btn" onClick={() => setAskReason("skip")}><Kbd>S</Kbd> Скип</button>
                  <button className="btn btn-danger" onClick={() => setAskReason("stoplist")}><Kbd>X</Kbd> Стоп-лист</button>
                </>
              )}
              {editMode && (
                <div className="confirm-edit">
                  <input value={editSubject} onChange={(e) => setEditSubject(e.target.value)} placeholder="Тема" />
                  <textarea rows={12} value={editBody} onChange={(e) => setEditBody(e.target.value)} />
                  <div className="row">
                    <button className="btn btn-primary" disabled={decide.isPending}
                            onClick={() => decide.mutate({ action: "edit", subject: editSubject, body: editBody })}>
                      Сохранить правку и отправить
                    </button>
                    <button className="btn btn-ghost" onClick={() => setEditMode(false)}>Отмена</button>
                    <span className="muted small">диф сохранится как золотая пара для калибровки промптов</span>
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
          </div>
        </div>
      )}
    </div>
  );
}
