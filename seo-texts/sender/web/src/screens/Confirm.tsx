// Экран «Подтвердить отправку» (ENGINEER-TASKS-CONFIRM-SEND, Задачи 2/4).
// Рендерит ТОТ ЖЕ JSON build_panel(), что и CLI confirm-show — паритет.
// Порядок блоков по линзе UX: стоп-флаги -> скоринг -> повод -> контакт ->
// компания -> письмо -> KB -> комплаенс -> действия. Хоткеи: Enter/E/S/X.
// ⛔ Холд: «Отправить» лишь переводит письмо в очередь (scheduled) — SMTP нет.

import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import type { ConfirmPanel, ConfirmReview, DialogItem, Proverki } from "../api/types";
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
  const news = p.news_events;
  // Выжимка, на которой писалось письмо: без неё оператор видит только ярлык
  // «модернизация» и не понимает, о чём вообще речь и почему мы пишем сейчас.
  const digest = p.news_digest || "";
  const digestUrl = p.news_url || "";
  if (!sig.present && !digest && !(news?.events || []).length) {
    return (
      <Card title="Новость-повод">
        <span className="muted">{sig.label || "повода нет — холодный заход"}</span>
      </Card>
    );
  }
  const t = sig.top;
  return (
    <Card title="Новость-повод">
      {digest && (
        <div className="news-digest">
          <div className="kv-key">о чём новость</div>
          <div>{digest}</div>
          {digestUrl && (
            <a href={digestUrl} target="_blank" rel="noreferrer">читать источник ↗</a>
          )}
        </div>
      )}
      {t && (
        <div className="kv-list" style={{ marginTop: digest ? "var(--sp-3)" : 0 }}>
          <Row label="событие">
            {t.event_type}{t.sum ? <> · <b>{t.sum}</b></> : null}
          </Row>
          <Row label="подробнее">{t.what}</Row>
          <Row label="когда">
            {t.date} <span className="muted" title={`важность ${t.hotness} из 5`}>{t.stars}</span>
          </Row>
          {t.source_url && !digestUrl && (
            <Row label="источник">
              <a href={t.source_url} target="_blank" rel="noreferrer">открыть ↗</a>
            </Row>
          )}
        </div>
      )}
      {(news?.events || []).length > 1 && (
        <details style={{ marginTop: "var(--sp-2)" }}>
          <summary className="muted">все новости компании ({news!.count})</summary>
          <div className="news-list">
            {news!.events.map((e, i) => (
              <div key={i} className="news-item">
                <div>
                  <b>{e.event_type}</b>
                  {e.sum ? <> · {e.sum}</> : null}
                  {e.date ? <span className="muted"> · {e.date}</span> : null}
                </div>
                <div>{e.what}</div>
                <div className="muted">
                  {e.source_name}
                  {e.source_url && (
                    <> · <a href={e.source_url} target="_blank" rel="noreferrer">источник ↗</a></>
                  )}
                  {!e.match_ok && (
                    <span className="soft-warn"> · названия компании в тексте нет — проверьте, её ли это новость</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </details>
      )}
    </Card>
  );
}

// Роль контакта словами: продажнику важно не название поля в базе, а решает
// ли этот человек закупку.
const ROLE_RU: Record<string, string> = {
  "снабжение/закупки": "снабжение и закупки — решает закупку",
  "гл.инженер": "главный инженер — решает по оборудованию",
  "директор": "директор",
  "продажи": "отдел продаж — не профильный, но человек живой",
  "общий": "общий ящик компании",
  "приёмная": "приёмная",
  "бухгалтерия": "бухгалтерия — не профильный",
  "кадры": "отдел кадров — не профильный",
};
// «откуда знаем» контакта приходит готовой строкой c.provenance с бэка — там
// честный разбор emails.source, а не статус сайта (раньше verified=provider
// печатал «подтверждено разбором сайта» даже когда сайта в карточке не было).
const LPR_RU: Record<string, string> = {
  match: "имя совпало с контактом в базе",
  mismatch: "в базе указан другой человек — проверьте, кому пишете",
  impersonal: "письмо безличное, конкретный человек не указан",
  no_data: "имя контактного лица неизвестно",
};

/** Строка «поле — значение»: в правой колонке было сплошное полотно текста. */
function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="kv-row">
      <span className="kv-key">{label}</span>
      <span className="kv-val">{children}</span>
    </div>
  );
}

export function ContactCard({ p, proverki }: { p: ConfirmPanel; proverki?: Proverki }) {
  const c = p.contact;
  // Проба адреса — отдельной строкой рядом с адресом. Строка «адрес живой»
  // ниже говорит только про MX домена, и 11.08 стало видно, чего это стоит:
  // домен kk@vebfabrika.ru почту «принимает», а ящика нет — письмо вернулось.
  const проба = proverki?.punkty.find((x) => x.код === "proba");
  // Панель может прийти неполной (письма ИИ-генерации какое-то время клались в
  // очередь с одним лишь ai-блоком). Раньше это был не «пустой блок», а падение
  // всего экрана: чтение c.lpr у undefined роняло React, и оператор видел белый
  // экран вместо очереди. Отсутствие данных показываем явно.
  if (!c) return <Card title="Кому пишем"><span className="soft-bad">нет данных контакта в карточке</span></Card>;
  const role = ROLE_RU[c.role] || c.role || "роль неизвестна";
  return (
    <Card title="Кому пишем">
      <div className="kv-list">
        <Row label="адрес"><b>{c.email}</b></Row>
        <Row label="кто это">
          {c.person ? <>{c.person} · {role}</> : role}
          {c.router && (
            <div className="soft-warn">
              это общий ящик — до человека, который решает, письмо может не дойти
            </div>
          )}
        </Row>
        <Row label="имя">{LPR_RU[c.lpr] || c.lpr || "—"}</Row>
        <Row label="почтовый сервер">
          {c.mx_ok === false ? <span className="soft-bad">нет, у домена нет почтового сервера</span>
            : c.mx_ok ? "у домена есть, письму есть куда идти" : "не проверялся"}
        </Row>
        {проба && (
          <Row label="сам ящик">
            <span className={проба.статус === "ok" ? "" :
                             проба.статус === "bad" ? "soft-bad" : "soft-warn"}>
              {проба.знак} {проба.podpis}
            </span>
          </Row>
        )}
        <Row label="откуда знаем">
          {c.source_link
            ? <a href={c.source_link} target="_blank" rel="noreferrer"
                 title={c.source || ""}>
                {c.provenance}{c.source_link_kind === "domain" ? " (домен)" : ""} ↗
              </a>
            : (c.provenance || c.source || "источник не указан")}
          {c.provenance_conflict && (
            <div className="soft-bad">
              источник контакта не подтверждён — проверьте вручную
            </div>
          )}
        </Row>
      </div>
      {c.domain_mismatch && (
        <div className="soft-warn">
          домен письма {c.email_domain} не совпадает с сайтом {c.site_domain} — проверьте адрес
        </div>
      )}
    </Card>
  );
}

export function CompanyCard({ p }: { p: ConfirmPanel }) {
  const c = p.company;
  if (!c) return <Card title="Компания"><span className="soft-bad">нет данных компании в карточке</span></Card>;
  const full = p.company_full;
  const reg = full?.reg || {};
  const fin = full?.fin || {};
  const prio = full?.priority || {};
  const prod = full?.product || {};
  // ОКВЭД с названиями: в базе обзвона коды хранятся сжатыми («25.62|25.11»),
  // расшифровка приходит отдельным полем — оператору нужны названия, не цифры.
  const okvedy = full?.okved_decoded || [];
  const okvedОсн = okvedy.find((o) => o.code === (c.okved || reg.okved_main))?.name
    || full?.okved_main_name;
  const div = c.division === "meyer" ? "Meyer — рентген и фотосепараторы"
    : c.division === "kc" ? "Компрессор Центр"
    : c.division === "kc+meyer" ? "оба направления"
    : c.division_badge;
  // Выручка: сперва из базы обзвона (там она годовая, из отчётности), потом
  // из панели. Раньше показывалось «в базе нет данных» даже когда число есть.
  const выручка = c.revenue ? c.revenue_h
    : (fin.revenue || fin.revenue_rub || null);
  return (
    <Card title="Компания">
      <div className="company-grid">
        <div className="kv-list">
          <Row label="название">
            <b>{c.name || reg.name_short || "—"}</b>
            {c.inn && <div className="muted">ИНН {c.inn}
              {reg.ogrn ? ` · ОГРН ${reg.ogrn}` : ""}</div>}
            {reg.name_full && reg.name_full !== c.name && (
              <div className="muted small">{reg.name_full}</div>)}
          </Row>
          <Row label="регион">{c.region || reg.region || "не указан"}</Row>
          {reg.address && <Row label="адрес">{reg.address}</Row>}
          <Row label="выручка">
            {выручка
              ? <>{выручка}{fin.god_otch ? <span className="muted"> за {fin.god_otch}</span> : null}</>
              : <span className="muted">в базе нет данных</span>}
          </Row>
          {(fin.profit || fin.ssch) && (
            <Row label="ещё из отчётности">
              {fin.profit ? `прибыль ${fin.profit}` : ""}
              {fin.profit && fin.ssch ? " · " : ""}
              {fin.ssch ? `сотрудников ${fin.ssch}` : ""}
            </Row>
          )}
          {(c.director || reg.director) && (
            <Row label="директор">{c.director || reg.director}</Row>)}
          {reg.status && <Row label="статус в ЕГРЮЛ">{reg.status}</Row>}
        </div>

        <div className="kv-list">
          <Row label="ОКВЭД">
            {c.okved || reg.okved_main || "—"}
            {okvedОсн && <span className="muted"> — {okvedОсн}</span>}
            {okvedy.length > 0 ? (
              <details>
                <summary className="muted">все коды ({okvedy.length})</summary>
                <div className="kv-list small">
                  {okvedy.map((o) => (
                    <Row key={o.code} label={o.code}>
                      {o.name || <span className="muted">названия нет в справочнике</span>}
                    </Row>
                  ))}
                </div>
              </details>
            ) : reg.okved_all_codes ? (
              <details><summary className="muted">все коды</summary>
                <div className="muted small">{reg.okved_all_codes}</div>
              </details>
            ) : null}
          </Row>
          <Row label="чем занимается">
            {c.activity || full?.activity || <span className="muted">описание не собрано</span>}
            {c.activity_verified === false && c.activity_note && (
              <div className="soft-warn">{c.activity_note}</div>
            )}
          </Row>
          <Row label="наше направление">
            {div}
            {full?.division_source && (
              <span className="muted"> (по {full.division_source === "obzvon"
                ? "метке базы" : full.division_source})</span>)}
          </Row>
          {/* Единый формат потребности (как в базе обзвона) для компаний вне
              базы: канонический текст «Оборудование по основному ОКВЭД» */}
          {c.equip_needed && (
            <Row label="какое оборудование необходимо">
              <b>{c.equip_needed}</b>
              {c.equip_needed_basis && (
                <div className="muted small">{c.equip_needed_basis}</div>)}
            </Row>
          )}
          {/* Ради этого поля всё и затевалось: что компании реально нужно */}
          {prod.equip_categories && (
            <Row label="что может пригодиться">
              <b>{prod.equip_categories}</b>
              {prod.calc_comment && (
                <div className="muted small">{prod.calc_comment}</div>)}
            </Row>
          )}
          {prod.found_okveds && (
            <Row label="целевые ОКВЭД">
              <span className="muted small">{prod.found_okveds}</span>
            </Row>
          )}
          <Row label="зачем компрессор">
            {c.why_equipment}
            {c.why_basis && <div className="muted">вывод по: {c.why_basis}</div>}
          </Row>
          {(prio.priority_max || prio.priority_total) && (
            <Row label="балл базы обзвона">
              макс {prio.priority_max || "—"} · сумма {prio.priority_total || "—"}
            </Row>
          )}
          {c.site && <Row label="сайт">
            <a href={c.site.startsWith("http") ? c.site : `https://${c.site}`}
               target="_blank" rel="noreferrer">{c.site}</a>
          </Row>}
        </div>
      </div>
      {full && !full.in_obzvon && (
        <div className="soft-warn">компании нет в базе обзвона — часть данных недоступна</div>
      )}
    </Card>
  );
}

/** Ответ клиенту: письмо, НА КОТОРОЕ отвечаем, и вердикты ревьюеров.
 *  Автоответчик кладёт это в карточку (reply_pipeline._panel), но экран их не
 *  рисовал: оператор видел текст ответа, не видя ни исходного письма, ни того,
 *  что о черновике сказали проверяющие линзы. */
const REPLY_KIND_RU: Record<string, string> = {
  interested: "заинтересован",
  question: "вопрос",
  price: "просит цену",
  refuse: "отказ",
  unsubscribe: "просит не писать",
  auto: "автоответ",
  other: "прочее",
};

function IncomingCard({ p }: { p: ConfirmPanel }) {
  const inc = p.incoming;
  if (!inc) return null;
  return (
    <Card title="Письмо клиента — на него отвечаем">
      <div className="kv-list">
        <Row label="от кого">{inc.from}</Row>
        <Row label="о чём">{REPLY_KIND_RU[inc.classified] || inc.classified || "не определено"}</Row>
        {inc.phone && <Row label="телефон в письме">{inc.phone}</Row>}
      </div>
      {inc.snippet && <pre className="confirm-letter">{inc.snippet}</pre>}
    </Card>
  );
}

// Ветка переписки с компанией — у черновиков ответа (kind='reply'): оператор
// отвечает, видя всю историю, а не только последнее входящее.
const THREAD_KIND_RU: Record<string, string> = {
  sent: "мы написали",
  reply_sent: "мы ответили",
  reply: "ответ клиента",
  reply_auto: "автоответ клиента",
  complaint: "жалоба",
  bounce: "письмо не доставлено",
  dsn: "отчёт о доставке",
};

// Сколько знаков письма видно в свёрнутом виде (примерно экран текста). Раньше
// тут стоял бокс maxHeight:180 — письмо клиента обрывалось на пятой строке, и
// развернуть его было нечем. Полный текст приходит с бэка всегда.
const THREAD_COLLAPSE_AT = 1200;

function ThreadItem({ t, openAll }: { t: DialogItem; openAll: boolean }) {
  const [open, setOpen] = useState(false);
  const body = t.body || "";
  const развернуто = open || openAll;
  const длинное = body.length > THREAD_COLLAPSE_AT;
  const показ = длинное && !развернуто ? body.slice(0, THREAD_COLLAPSE_AT) : body;
  return (
    <div className={`dialog-item dialog-${t.direction}`}>
      <div className="muted small">
        {THREAD_KIND_RU[t.kind] || t.kind} · {(t.ts || "").slice(0, 16).replace("T", " ")}
        {t.mailbox_id ? ` · ящик ${t.mailbox_id}` : ""}
        {t.email ? ` · ${t.email}` : ""}
      </div>
      {t.subject && <div><b>{t.subject}</b></div>}
      {body && (
        <pre className="confirm-letter">
          {показ}{длинное && !развернуто ? "…" : ""}
        </pre>
      )}
      {t.body_missing && (
        <div className="muted small">
          текст письма не сохранён — в журнале отправок осталась только тема
        </div>
      )}
      {t.body_truncated && (
        <div className="muted small">
          письмо длиной {t.body_len} знаков — показаны первые {body.length}
        </div>
      )}
      {длинное && !openAll && (
        <button className="btn btn-ghost btn-sm" onClick={() => setOpen(!open)}>
          {open ? "свернуть" : `показать целиком (${body.length} знаков)`}
        </button>
      )}
    </div>
  );
}

function ThreadCard({ thread }: { thread?: DialogItem[] }) {
  const [openAll, setOpenAll] = useState(false);
  if (!thread || thread.length === 0) return null;
  const длинные = thread.filter((t) => (t.body || "").length > THREAD_COLLAPSE_AT).length;
  return (
    <Card title={`Переписка (${thread.length})`}>
      {длинные > 0 && (
        <div className="row">
          <button className="btn btn-ghost btn-sm" onClick={() => setOpenAll(!openAll)}>
            {openAll ? "свернуть длинные письма" : `развернуть всю переписку (${длинные})`}
          </button>
        </div>
      )}
      <div className="news-list">
        {thread.map((t, i) => (
          <ThreadItem key={`${t.source || ""}:${t.message_id ?? t.event_id ?? t.review_id ?? i}`}
                      t={t} openAll={openAll} />
        ))}
      </div>
    </Card>
  );
}

// Все контакты компании с ИСТОЧНИКОМ каждого: владелец увидел в списке чужой
// газпромовский адрес и попросил «провалиться на страницу, откуда он взялся».
function ContactsSourceCard({ p }: { p: ConfirmPanel }) {
  const list = p.emails || [];
  if (list.length === 0) return null;
  const свой = (p.company?.site || "").replace(/^https?:\/\//, "").split("/")[0];
  return (
    <Card title={`Контакты компании (${list.length}) — откуда взяты`}>
      <div className="kv-list">
        {list.map((c, i) => {
          const дом = (c.email || "").split("@")[1] || "";
          const чужой = свой && дом && !свой.includes(дом) && !дом.includes(свой.replace("www.", ""));
          return (
            <Row key={i} label={c.role || "роль не указана"}>
              <span className={чужой ? "soft-warn" : ""}>{c.email}</span>
              {c.person ? <span className="muted"> · {c.person}</span> : null}
              {c.source_url
                ? <> · <a href={c.source_url} target="_blank" rel="noreferrer">
                    {c.source || "источник"} ↗</a></>
                : (c.source ? <span className="muted"> · {c.source}</span> : null)}
              {чужой && <div className="soft-warn">домен {дом} не совпадает с сайтом компании — проверьте, её ли это контакт</div>}
            </Row>
          );
        })}
      </div>
    </Card>
  );
}

function ReviewCard({ p }: { p: ConfirmPanel }) {
  const rv = p.review;
  if (!rv) return null;
  const dec = rv.decision === "SEND" ? "проверяющие за отправку"
    : rv.decision === "ESCALATE" ? "проверяющие требуют решения человека"
    : rv.decision || "решение не записано";
  return (
    <Card title="Что сказали проверяющие">
      <div className={rv.decision === "SEND" ? "soft-ok" : "soft-warn"}>{dec}</div>
      {rv.escalate_reason && <div>причина: {rv.escalate_reason}</div>}
      {(rv.qa_problems || []).length > 0 && (
        <div className="soft-warn">замечания: {(rv.qa_problems || []).join("; ")}</div>
      )}
      {(rv.verdicts || []).length > 0 && (
        <details style={{ marginTop: "var(--sp-2)" }}>
          <summary className="muted">разбор по линзам ({rv.verdicts!.length})</summary>
          <div className="news-list">
            {rv.verdicts!.map((v, i) => (
              <div key={i} className="news-item">
                <div><b>{v.lens || v.name || `линза ${i + 1}`}</b>
                  {" — "}
                  {v.ok === false ? <span className="soft-warn">замечания есть</span>
                    : v.ok === true ? <span className="soft-ok">чисто</span> : null}
                </div>
                {(v.problems || []).length > 0 && <div>{(v.problems || []).join("; ")}</div>}
              </div>
            ))}
          </div>
        </details>
      )}
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
  // picked переживает F5: оператор смотрел не первое письмо, обновил страницу —
  // раньше сбрасывало на первое (состояние жило только в памяти).
  const [picked, setPickedRaw] = useState<number | null>(() => {
    const v = Number(localStorage.getItem("confirm_picked"));
    return Number.isFinite(v) && v > 0 ? v : null;
  });
  const setPicked = (id: number | null) => {
    setPickedRaw(id);
    if (id) localStorage.setItem("confirm_picked", String(id));
    else localStorage.removeItem("confirm_picked");
  };
  const [editSubject, setEditSubject] = useState("");
  const [editBody, setEditBody] = useState("");
  const [askReason, setAskReason] = useState<"skip" | "stoplist" | null>(null);
  const [reason, setReason] = useState("");

  // Очередь грузилась жёстко по 20 писем из 70: до своего адреса в хвосте
  // оператор просто не мог добраться. Теперь страница растёт кнопкой, а найти
  // конкретное письмо можно поиском по адресу, компании или ИНН.
  const [limit, setLimit] = useState(50);
  const [поиск, setПоиск] = useState("");
  // Фильтр КЦ/Meyer — ЛОКАЛЬНЫЙ для оператора (localStorage браузера, не
  // настройка аккаунта): с двумя базами работают разные люди одновременно.
  const [напр, setНапр] = useState<string>(
    () => localStorage.getItem("confirm_division") || "все");
  const выбратьНапр = (v: string) => {
    setНапр(v);
    localStorage.setItem("confirm_division", v);
  };
  // Фильтр по ГРУППЕ получателей (владелец 05.08: «сделай фильтр очереди по
  // группам — новостные, по металлам, ещё какие-то»). Считает СЕРВЕР, до
  // нарезки страницы: фильтруя на клиенте, мы фильтровали бы одну загруженную
  // страницу, а счётчик очереди показывал бы всё подряд — та же ошибка, из-за
  // которой фильтр направления в своё время переехал на сервер.
  // Выбор локальный для оператора, как и КЦ/Meyer: с базами работают разные люди.
  const [группа, setГруппа] = useState<string>(
    () => localStorage.getItem("confirm_gruppa") || "");
  const выбратьГруппу = (v: string) => {
    setГруппа(v);
    localStorage.setItem("confirm_gruppa", v);
  };
  const группы = useQuery({
    queryKey: ["confirm-groups"],
    queryFn: () => api.confirmGroups(),
    staleTime: 60000,
  });
  // «Скрыть ждущих созревания доменов» (владелец 06.08). Письма получателям на
  // СОБСТВЕННЫХ корпоративных серверах отправить сейчас нельзя — их шлюзы
  // отбивают почту с новых доменов («550 5.7.1 blocked due to security
  // reason»), и заслон на бэке их не выпустит. Показывать их оператору незачем,
  // поэтому по умолчанию прячем; выключатель рядом, состояние — локальное.
  const [прятатьЖдущих, setПрятатьЖдущих] = useState<boolean>(
    // По умолчанию ВЫКЛЮЧЕНА. Раньше было наоборот, и после снятия гейта
    // молодых доменов (09.08) галка стала прятать письма на корпоративные
    // серверы — владелец открыл очередь и не нашёл в ней 197 писем.
    () => localStorage.getItem("confirm_hide_blocked") === "1");
  const переключитьЖдущих = (v: boolean) => {
    setПрятатьЖдущих(v);
    localStorage.setItem("confirm_hide_blocked", v ? "1" : "0");
  };
  const queue = useQuery({
    queryKey: ["confirm-queue", limit, группа, прятатьЖдущих],
    queryFn: () => api.confirmQueue({ limit, ...(группа ? { gruppa: группа } : {}),
                                      ...(прятатьЖдущих ? { hide_blocked: true } : {}) }),
    // фоновая генерация (#71) доливает письма — очередь обновляется сама
    refetchInterval: 20000,
  });

  // #71: «сгенерировать ещё N писем в очередь» + перегенерация текущего
  const [genCount, setGenCount] = useState(14);
  const [regenId, setRegenId] = useState<number | null>(null);
  const genMore = useMutation({
    mutationFn: () => api.quotaRunCount(current?.campaign_id ?? 1, genCount),
    onSuccess: () => toast("success",
      `Генерация ${genCount} писем запущена — очередь пополнится по мере готовности`),
    onError: (e) => toast("error", e instanceof ApiError
      ? `Генерация: ${e.detail}` : "Ошибка генерации"),
  });
  // Кнопка «в автоотправку» (владелец 06.08): первые N писем очереди становятся
  // approved и уходят фоновому циклу — тот шлёт их САМ, по окну в зоне
  // получателя. Нажатие = включение автоотправки, поэтому диалог строгий,
  // а рядом виден тумблер «остановить».
  const [autoN, setAutoN] = useState(300);
  const autoSend = useQuery({
    queryKey: ["auto-send"],
    queryFn: () => api.autoSend(),
    refetchInterval: 30000,
  });
  const bulkToAuto = useMutation({
    mutationFn: () => api.confirmBulkToAuto(autoN, группа || undefined),
    onSuccess: (d) => {
      toast("success", `В автоотправку: ${d.moved}`
        + (d.skipped.length
           ? ` · пропущено ${d.skipped.length} (например: ${d.skipped[0].reason})`
           : ""));
      qc.invalidateQueries({ queryKey: ["confirm-queue"] });
      qc.invalidateQueries({ queryKey: ["auto-send"] });
    },
    onError: (e) => toast("error", e instanceof ApiError
      ? `Автоотправка: ${e.detail}` : "Ошибка автоотправки"),
  });
  const autoToggle = useMutation({
    mutationFn: (enabled: boolean) => api.autoSendSet(enabled),
    onSuccess: (d) => {
      toast(d.enabled ? "info" : "success",
            d.enabled ? "Автоотправка включена" : "Автоотправка остановлена");
      qc.invalidateQueries({ queryKey: ["auto-send"] });
    },
  });
  const regen = useMutation({
    mutationFn: (rid: number) => api.confirmRegenerate(rid),
    onSuccess: (_d, rid) => {
      setRegenId(rid);
      toast("info", `Письмо #${rid} ушло на перегенерацию`);
    },
    onError: (e) => toast("error", e instanceof ApiError
      ? `Перегенерация: ${e.detail}` : "Ошибка"),
  });
  // поллинг статуса перегенерации: по готовности обновляем очередь
  useQuery({
    queryKey: ["confirm-regen", regenId],
    queryFn: async () => {
      const st = await api.confirmRegenerateStatus(regenId!);
      if (!st.running) {
        setRegenId(null);
        if (st.error) toast("error", `Перегенерация: ${st.error}`);
        else {
          toast("success", `Письмо #${regenId} перегенерировано`);
          qc.invalidateQueries({ queryKey: ["confirm-queue"] });
        }
      }
      return st;
    },
    enabled: regenId != null,
    refetchInterval: 5000,
  });
  // Раньше показывалось жёстко первое письмо очереди: перейти к конкретному
  // было нельзя, а в очереди десятки писем. Теперь слева список, справа
  // карточка; выбранное запоминается, пока оно в очереди.
  const list: ConfirmReview[] = queue.data?.pending || [];
  const запрос = поиск.trim().toLowerCase();
  const поНапр: ConfirmReview[] = напр === "все" ? list
    : list.filter((r) => {
        const d = ((r.panel as ConfirmPanel)?.company?.division || "").toLowerCase();
        if (!d) return true;               // без направления — видно всем
        return d.includes(напр);           // kc+meyer попадает в оба фильтра
      });
  const показ: ConfirmReview[] = запрос
    ? поНапр.filter((r) =>
        (r.email || "").toLowerCase().includes(запрос) ||
        ((r.panel as ConfirmPanel)?.company?.name || "").toLowerCase().includes(запрос) ||
        String(r.inn || "").includes(запрос))
    : поНапр;
  const current: ConfirmReview | undefined =
    показ.find((r) => r.id === picked) || показ[0] ||
    list.find((r) => r.id === picked) || list[0];
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

  // Свободный ввод адреса: контакт того же предприятия, которого нет в
  // карточке. Отдельная мутация от setRecipient — там allow-лист карточки,
  // здесь адрес заводится в базу под ИНН карточки после проверок движка.
  const [новыйАдрес, setНовыйАдрес] = useState("");
  // Копия этого же письма на другой адрес: исходное остаётся на месте.
  const [копияАдрес, setКопияАдрес] = useState("");
  // Письмо с нуля — «чтобы работало просто как почта» (владелец 11.08).
  const [пишемСам, setПишемСам] = useState(false);
  const [самЯщик, setСамЯщик] = useState("");
  const [самКому, setСамКому] = useState("");
  const [самТема, setСамТема] = useState("");
  const [самТекст, setСамТекст] = useState("");
  const [легендаВидна, setЛегендаВидна] = useState(false);
  // Копия ЭТОГО ЖЕ письма на другой адрес. Нужна, когда автоответ назвал
  // имя коллеги, а оператор знает общую почту компании: исходное письмо
  // остаётся в очереди, рядом появляется копия с тем же текстом.
  const kopiya = useMutation({
    mutationFn: (email: string) => api.confirmKopiya(current!.id, email),
    onSuccess: (d) => {
      setКопияАдрес("");
      toast("success", `Копия письма поставлена в очередь: ${d.email}`);
      qc.invalidateQueries({ queryKey: ["confirm-queue"] });
    },
    onError: (e: Error) => toast("error", `Копия не создалась: ${e.message}`),
  });

  // Письмо с нуля: ящик, адрес, тема, текст. Ложится в ту же очередь и той
  // же кнопкой отправляется — это вход в ручной режим, а не обход его.
  const novoe = useMutation({
    mutationFn: () => api.confirmNovoe({
      email: самКому.trim(), subject: самТема.trim(), body: самТекст,
      ...(самЯщик ? { mailbox_id: самЯщик } : {}),
    }),
    onSuccess: (d) => {
      setПишемСам(false);
      setСамКому(""); setСамТема(""); setСамТекст("");
      toast("success", `Письмо создано и ждёт отправки: ${d.email}`);
      qc.invalidateQueries({ queryKey: ["confirm-queue"] });
    },
    onError: (e: Error) => toast("error", `Письмо не создалось: ${e.message}`),
  });

  const addRecipient = useMutation({
    mutationFn: (email: string) => api.confirmAddRecipient(current!.id, email),
    onSuccess: (d, email) => {
      setНовыйАдрес("");
      toast("success", d.created_recipient
        ? `Контакт заведён и выбран: ${email}`
        : `Адрес выбран (в базе уже был): ${email}`);
      qc.invalidateQueries({ queryKey: ["confirm-queue"] });
    },
    onError: (err) => {
      // 403 — фича выключена настройкой, 409 — комплаенс (стоп-лист, чужой
      // ИНН), 400 — формат или статус карточки. Показываем причину как есть:
      // оператору важно, ЧТО именно не пустило, а не общее «ошибка».
      if (err instanceof ApiError) toast("error", `Новый адрес: ${err.detail}`);
      else toast("error", `Новый адрес: ${(err as Error).message}`);
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
    onError: (err, vars) => {
      if (err instanceof ApiError && err.status === 409) {
        // Заслон мог появиться уже ПОСЛЕ постановки в очередь — тогда
        // стоп-флагов в карточке нет и первый диалог не сработал. Предлагаем
        // обойти прямо здесь: это и есть второе подтверждение оператора.
        if (!vars.force && (vars.action === "approve" || vars.action === "edit")
            && window.confirm(`Заслон: ${err.detail}\n\nОтправить вручную `
                              + "ВСЁ РАВНО? Обход попадёт в аудит.")) {
          decide.mutate({ ...vars, force: true });
          return;
        }
        toast("error", `Заслон: ${err.detail}`);
      } else {
        toast("error", `Ошибка: ${(err as Error).message}`);
      }
    },
  });

  const doApprove = useCallback(() => {
    if (!current || decide.isPending || regenId === current.id) return;
    // Стоп-флаги карточки — предупреждение ДО отправки (что знали на момент
    // постановки в очередь). force здесь НЕ шлём: флаги могли быть жёлтыми
    // (вне базы при ВКЛ-тумблере), а force снимает ВСЕ заслоны разом — в том
    // числе отписку, появившуюся ПОЗЖЕ, о которой оператор ничего не знает.
    // Первый запрос всегда без force: если заслон реально действует СЕЙЧАС,
    // бэкенд ответит 409 с настоящей причиной, и уже ТОТ диалог (onError) —
    // второе подтверждение обхода, с перечислением того, что обходим.
    const flags = (panel.stop_flags || []).map((f) => f.label).join("; ");
    if (holdNeeded && !window.confirm(
        "Стоп-флаги: " + (flags || "есть стоп-флаги")
        + "\n\nПродолжить отправку?")) return;
    decide.mutate({ action: "approve", force: false });
  }, [current, decide, holdNeeded, panel, regenId]);

  // Хоткеи: ОТПРАВКА только по Ctrl/Cmd+Enter, остальное — E/S/X.
  //
  // Голый Enter здесь недопустим: confirm.live_send=true, то есть подтверждение
  // это НЕМЕДЛЕННАЯ боевая отправка живому юрлицу. В карточке появились
  // выпадающие списки «с ящика» и «кому», а в них Enter — штатная клавиша
  // выбора: одно нажатие уходило бы письмом. Плюс зажатый Enter повторяется
  // (e.repeat) и мог отправить несколько писем подряд.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement | null;
      const tag = el?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT"
          || el?.isContentEditable || editMode || askReason) return;
      if (!current || e.repeat) return;
      if (e.key === "Enter") {
        if (!(e.ctrlKey || e.metaKey)) return;   // голый Enter не отправляет
        e.preventDefault();
        doApprove();
      }
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
          {/* Живая отправка ставит статус sent, а не approved — счётчик
              «одобрено» вечно показывал 0 при реально ушедших письмах (#60) */}
          в очереди: {counts.pending || 0} ·
          отправлено: {(counts.sent || 0) + (counts.approved || 0)} ·
          правок: {counts.edited || 0} · скипов: {counts.skipped || 0} ·
          стоп-лист: {counts.stoplist || 0}
          {(counts.reply_pending || 0) > 0 && (
            <span className="confirm-reply-badge" title="клиент ответил и ждёт">
              ✉ {counts.reply_pending} для ответа
            </span>
          )}
        </div>
        <div className="chips">
          {["все", "kc", "meyer"].map((v) => (
            <label key={v} className={`chip${напр === v ? " on" : ""}`}>
              <input type="radio" name="div-filter" checked={напр === v}
                     onChange={() => выбратьНапр(v)} />
              {v === "все" ? "Все" : v === "kc" ? "КЦ" : "Meyer"}
            </label>
          ))}
        </div>
        <div className="row">
          <label className="muted">
            группа:{" "}
            <select value={группа} onChange={(e) => выбратьГруппу(e.target.value)}>
              <option value="">все группы</option>
              {(группы.data?.groups || []).map((g) => (
                <option key={g.name} value={g.name}>
                  {g.name} ({g.recipients})
                </option>
              ))}
            </select>
          </label>
          {группа && (
            <span className="muted"> · писем в группе: {queue.data?.total ?? показ.length}</span>
          )}
          <label className="muted" style={{ marginLeft: 12 }}
                 title="письма получателям на СОБСТВЕННЫХ почтовых серверах: их шлюзы строже к письмам с молодых доменов. Отправлять можно — решаете вы">
            <input type="checkbox" checked={прятатьЖдущих}
                   onChange={(e) => переключитьЖдущих(e.target.checked)} />
            {" "}скрыть письма на корпоративные серверы
            {(queue.data?.corp_total || 0) > 0 && (
              <span> · таких {queue.data?.corp_total}</span>
            )}
            {(queue.data?.blocked_hidden || 0) > 0 && (
              <span> · скрыто {queue.data?.blocked_hidden}
                {queue.data?.blocked_until ? `, до ${queue.data.blocked_until}` : ""}</span>
            )}
          </label>
        </div>
        <div className="row">
          {/* #71: поднял дневной лимит — добей очередь под него */}
          <input type="number" min={1} max={200} value={genCount}
                 style={{ width: 64 }}
                 onChange={(e) => setGenCount(Number(e.target.value) || 1)} />
          <button className="btn" disabled={genMore.isPending}
                  onClick={() => genMore.mutate()}>
            Сгенерировать в очередь
          </button>
          <button className="btn" style={{ marginLeft: 8 }}
                  title="написать письмо самому: ящик, адрес, тема, текст"
                  onClick={() => setПишемСам((v) => !v)}>
            {пишемСам ? "Закрыть" : "Написать письмо"}
          </button>
          <button type="button" className="btn-link muted"
                  style={{ marginLeft: 8 }}
                  onClick={() => setЛегендаВидна((v) => !v)}>
            {легендаВидна ? "скрыть значки" : "что значат значки"}
          </button>
        </div>
        {легендаВидна && (
          <div className="confirm-legenda">
            {(queue.data?.proverki_legenda || []).map((л) => (
              <div key={л.код} className="cl-row">
                <span className="cl-znak">{л.значок}</span>
                <b>{л.имя}</b>
                <span className="muted"> — {л.что}</span>
              </div>
            ))}
            <div className="cl-row muted small">
              ✅ проверка пройдена · ⚠️ есть оговорка · ❌ не пройдена ·
              {" "}❔ НЕ проверялось (это не «всё хорошо», а «мы не знаем»)
            </div>
          </div>
        )}
        {пишемСам && (
          <div className="confirm-novoe">
            <div className="row">
              <label>с ящика:{" "}
                <select value={самЯщик} onChange={(e) => setСамЯщик(e.target.value)}>
                  <option value="">(выберет система)</option>
                  {(current?.send_as?.options || []).map((m) => (
                    <option key={m.mailbox_id} value={m.mailbox_id}
                            disabled={!m.available}>
                      {m.from_name ? `${m.from_name} <${m.mailbox_id}>` : m.mailbox_id}
                      {m.available ? "" : " — недоступен"}
                    </option>
                  ))}
                </select>
              </label>
              <input type="email" placeholder="кому: адрес почты"
                     style={{ minWidth: 260, marginLeft: 8 }}
                     value={самКому} onChange={(e) => setСамКому(e.target.value)} />
            </div>
            <input type="text" placeholder="тема письма"
                   style={{ width: "100%", marginTop: 6 }}
                   value={самТема} onChange={(e) => setСамТема(e.target.value)} />
            <textarea placeholder="текст письма" rows={8}
                      style={{ width: "100%", marginTop: 6 }}
                      value={самТекст} onChange={(e) => setСамТекст(e.target.value)} />
            <div className="row" style={{ marginTop: 6 }}>
              <button className="btn primary"
                      disabled={novoe.isPending || !самКому.trim()
                                || !самТема.trim() || !самТекст.trim()}
                      onClick={() => novoe.mutate()}>
                {novoe.isPending ? "создаю…" : "В очередь на отправку"}
              </button>
              <span className="muted small" style={{ marginLeft: 10 }}>
                письмо ляжет в очередь и уйдёт по кнопке «Отправить» — как все
                остальные, со всеми заслонами
              </span>
            </div>
          </div>
        )}
        <div className="row">
          {/* переброска очереди в автоотправку (владелец 06.08) */}
          <input type="number" min={1} max={300} value={autoN}
                 style={{ width: 72 }}
                 onChange={(e) => setAutoN(
                   Math.max(1, Math.min(300, Number(e.target.value) || 1)))} />
          <button className="btn"
                  disabled={bulkToAuto.isPending || !queue.data?.live}
                  title={queue.data?.live ? "первые N писем очереди уйдут в автоотправку"
                    : "живая отправка выключена (confirm.live_send)"}
                  onClick={() => {
                    if (!window.confirm(
                      `АВТООТПРАВКА: первые ${autoN} писем очереди`
                      + (группа ? ` группы «${группа}»` : "")
                      + " будут одобрены и отправлены АВТОМАТИЧЕСКИ, без ручного"
                      + " подтверждения каждого — в рабочее окно по времени"
                      + " получателя. Продолжить?")) return;
                    bulkToAuto.mutate();
                  }}>
            В автоотправку (первые {autoN})
          </button>
          {autoSend.data && (
            <span className="muted small">
              {" "}автоотправка: {autoSend.data.enabled
                ? (autoSend.data.running ? "ВКЛ" : "ВКЛ (цикл не запущен!)")
                : "выкл"}
              {autoSend.data.enabled && (
                <button className="btn" style={{ marginLeft: 6 }}
                        disabled={autoToggle.isPending}
                        onClick={() => autoToggle.mutate(false)}>
                  остановить
                </button>
              )}
            </span>
          )}
        </div>
      </div>

      {!current && (
        <Empty hint={группа
          ? `В группе «${группа}» писем в очереди нет — выберите другую группу или «все группы».`
          : "Очередь подтверждений пуста — калибровать нечего."} />
      )}

      {current && (
        <div className="confirm-layout">
        <aside className="confirm-queue">
          <div className="confirm-queue-head">
            письма в очереди · {показ.length}
            {показ.length !== list.length && <span className="muted"> из {list.length}</span>}
            {queue.data?.live && <span className="confirm-mode-live">живая отправка</span>}
          </div>
          <div className="confirm-queue-find">
            <input type="search" value={поиск} placeholder="найти: адрес, компания, ИНН"
                   onChange={(e) => setПоиск(e.target.value)} />
          </div>
          <div className="confirm-queue-list">
            {показ.length === 0 && (
              <div className="muted small" style={{ padding: "8px 10px" }}>
                ничего не нашлось{list.length < (counts.pending || 0)
                  ? " на загруженной части очереди — подгрузите остальные"
                  : ""}
              </div>
            )}
            {показ.map((r) => {
              const pnl = (r.panel || {}) as ConfirmPanel;
              const sc = pnl.scoring?.score;
              const flags = (pnl.stop_flags || []).length;
              return (
                <button key={r.id} type="button"
                        className={`confirm-queue-item${r.id === current.id ? " current" : ""}`}
                        onClick={() => setPicked(r.id)}>
                  <div className="qi-top">
                    <span className={`qi-dot ${pnl.scoring?.color || ""}`} />
                    <span className="qi-email">{r.email}</span>
                    {(r.kind || "") === "reply" && (
                      <span className="qi-flag" style={{ color: "var(--ok)" }}>ответ</span>
                    )}
                    {flags > 0 && <span className="qi-flag">стоп</span>}
                    {r.sent?.ever && <span className="qi-flag warn" title="этому адресу уже писали">писали</span>}
                  </div>
                  {/* Значков проверок в списке НЕТ намеренно (владелец 11.08:
                      «вот это убери»). Шесть значков под каждым адресом в
                      узкой колонке — это рябь, по которой всё равно ничего не
                      прочитать: список нужен, чтобы выбрать письмо, а разбор
                      проверок живёт справа, у самих адресов. */}
                  <div className="qi-sub">
                    {pnl.company?.name || r.inn || "—"}
                    {sc !== undefined ? ` · ${sc}` : ""}
                  </div>
                </button>
              );
            })}
          </div>
          {list.length < (counts.pending || 0) && (
            <button type="button" className="confirm-queue-more"
                    disabled={queue.isFetching}
                    onClick={() => setLimit(limit + 50)}>
              {queue.isFetching ? "гружу…"
                : `показать ещё (осталось ${(counts.pending || 0) - list.length})`}
            </button>
          )}
        </aside>
        <div className="confirm-main">
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
                {/* Итог проверок прямо в строке выбора: оператор переключает
                    письмо между адресами, и состояние адреса надо видеть ДО
                    переключения, а не после (владелец 11.08). В option можно
                    положить только текст, поэтому здесь один общий знак, а
                    разбор по шести проверкам — строкой ниже. */}
                <option value={current.email}
                        title={(current.proverki?.punkty || [])
                          .map((x) => `${x.знак} ${x.имя}: ${x.podpis}`)
                          .join("\n")}>
                  {current.proverki?.znak ? `${current.proverki.znak} ` : ""}
                  {current.email}
                </option>
                {(panel.emails || [])
                  .filter((c) => c.email && c.email !== current.email)
                  .map((c) => {
                    const пр = current.proverki_adresov?.[c.email.toLowerCase()];
                    return (
                      <option key={c.email} value={c.email}
                              title={(пр?.punkty || [])
                                .map((x) => `${x.знак} ${x.имя}: ${x.podpis}`)
                                .join("\n")}>
                        {пр?.znak ? `${пр.znak} ` : ""}{c.email}
                        {c.role ? ` · ${c.role}` : ""}
                        {c.person ? ` · ${c.person}` : ""}
                      </option>
                    );
                  })}
              </select>
              {current.proverki && (
                <span className="qi-proverki qi-proverki-ryadom">
                  {current.proverki.punkty.map((x) => (
                    <span key={x.код} className={`qi-pv qi-pv-${x.статус}`}
                          title={`${x.имя}: ${x.podpis}`}>
                      {x.значок}<i className="qi-pv-znak">{x.знак}</i>
                    </span>
                  ))}
                </span>
              )}
            </label>
            {/* Вписать адрес, которого нет в карточке (контакт того же
                предприятия). Ручка была на сервере с 05.08 и пропала, когда
                фронт пересобрали из репо-исходников без неё; движок
                (/confirm/{id}/recipient/add) всё это время работал.
                Свободный ввод идёт именно сюда, а не в список выше: адрес
                сначала проверяется (формат, стоп-лист, не закреплён ли за
                чужим ИНН) и заводится в базу под ИНН карточки. */}
            <label>
              новый адрес:{" "}
              <input
                type="email"
                value={новыйАдрес}
                placeholder="ivanov@zavod.ru"
                style={{ width: 190 }}
                disabled={addRecipient.isPending}
                onChange={(e) => setНовыйАдрес(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && новыйАдрес.trim()) {
                    e.preventDefault();
                    addRecipient.mutate(новыйАдрес.trim());
                  }
                }}
              />{" "}
              <button className="btn"
                      disabled={addRecipient.isPending || !новыйАдрес.trim()}
                      onClick={() => addRecipient.mutate(новыйАдрес.trim())}>
                добавить и выбрать
              </button>
              <span className="muted small" style={{ marginLeft: 12 }}>
                или отправить ТО ЖЕ письмо на другой адрес, не трогая это:
              </span>
              <input type="email" placeholder="копия на адрес"
                     style={{ minWidth: 200, marginLeft: 6 }}
                     value={копияАдрес}
                     onChange={(e) => setКопияАдрес(e.target.value)}
                     onKeyDown={(e) => {
                       if (e.key === "Enter" && копияАдрес.trim()) {
                         e.preventDefault();
                         kopiya.mutate(копияАдрес.trim());
                       }
                     }} />
              <button className="btn" style={{ marginLeft: 6 }}
                      disabled={kopiya.isPending || !копияАдрес.trim()}
                      title="исходное письмо останется в очереди, рядом появится копия"
                      onClick={() => kopiya.mutate(копияАдрес.trim())}>
                {kopiya.isPending ? "…" : "копию сюда"}
              </button>
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
            <ContactCard p={panel} proverki={current.proverki} />
          </div>
          <CompanyCard p={panel} />

          <IncomingCard p={panel} />
          <ThreadCard thread={current.thread} />
          <ContactsSourceCard p={panel} />
          <ReviewCard p={panel} />
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
                {/* Пока письмо перегенерируется, отправка/правка закрыты и на
                    бэке (409): текст в БД может подмениться под рукой */}
                <button className="btn btn-primary"
                        disabled={decide.isPending || regenId === current.id}
                        onClick={doApprove}>
                  [Ctrl+Enter] Отправить{holdNeeded ? " (стоп-флаги!)" : ""}
                </button>
                <button className="btn" disabled={regenId === current.id}
                        onClick={() => { setEditSubject(current.subject); setEditBody(current.body); setEditMode(true); }}>
                  [E] Править
                </button>
                <button className="btn" onClick={() => setAskReason("skip")}>[S] Скип</button>
                <button className="btn btn-danger" onClick={() => setAskReason("stoplist")}>[X] Стоп-лист</button>
                <button className="btn" disabled={regenId != null || regen.isPending}
                        title="письмо уйдёт на генерацию заново и вернётся в очередь"
                        onClick={() => regen.mutate(current.id)}>
                  {regenId === current.id ? "⟳ Генерируется…" : "⟳ Перегенерировать"}
                </button>
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
        </div>
        </div>
      )}
    </div>
  );
}
