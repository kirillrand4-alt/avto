// Экран 6 — Лента лидов (эпицентр). Фильтры + таблица + [Взять] с оптимистичной
// блокировкой: 409/400 → тост «уже взял другой», строка гаснет. PII маскируется
// для менеджера до «Взять».

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuth } from "../context/auth";
import { useToast } from "../components/Toast";
import { Spinner, ErrorBox, Empty, StatusBadge, Pager } from "../components/ui";
import { maskEmail, maskPhone, replyBadge, ageHours } from "../lib/format";
import type { Lead } from "../api/types";

const REPLY_KINDS: Array<{ key: string; label: string }> = [
  { key: "", label: "все" },
  { key: "hot", label: "горячий" },
  { key: "interested", label: "интересуется" },
  { key: "auto_reply", label: "автоответ" },
  { key: "not_interested", label: "отказ" },
];
// Подписи, а не голые ключи: в выпадающем списке стояло «not_qualified».
const STATUSES: Array<{ key: string; label: string }> = [
  { key: "", label: "все" },
  { key: "new", label: "новый" },
  { key: "taken", label: "взят" },
  { key: "called", label: "позвонил" },
  { key: "qualified", label: "квалифицирован" },
  { key: "unqualified", label: "не квалифицирован" },
  { key: "in_bitrix", label: "отдали в Bitrix" },
  { key: "v_otpuske", label: "в отпуске" },
  { key: "avtootvet", label: "автоответ" },
  { key: "not_interested", label: "не интересно" },
  { key: "closed", label: "закрыт" },
];

// Куда можно перевести лид из текущего статуса. Список ПОВТОРЯЕТ движок
// (leaddesk._TRANSITIONS): показывать переход, который сервер отвергнет с
// «illegal lead transition», — обманывать оператора. Владелец 19.08: «сделай
// чтобы не крестик был, а можно было перекидывать из ленты в статусы».
const ПЕРЕХОДЫ: Record<string, string[]> = {
  new: ["taken", "in_bitrix", "v_otpuske", "avtootvet", "not_interested",
        "closed"],
  assigned: ["taken", "new", "v_otpuske", "avtootvet", "not_interested",
             "closed"],
  taken: ["called", "qualified", "unqualified", "in_bitrix", "v_otpuske",
          "avtootvet", "not_interested", "closed"],
  called: ["qualified", "unqualified", "in_bitrix", "v_otpuske", "avtootvet",
           "not_interested", "closed"],
  qualified: ["in_bitrix", "v_otpuske", "closed"],
  unqualified: ["new", "closed"],
  in_bitrix: ["closed"],
  not_interested: ["new", "closed"],
  v_otpuske: ["new", "taken", "called", "in_bitrix", "not_interested", "closed"],
  avtootvet: ["new", "taken", "v_otpuske", "in_bitrix", "not_interested",
              "closed"],
  closed: [],
};
const ПОДПИСЬ: Record<string, string> = {
  new: "вернуть в новые",
  assigned: "назначен",
  taken: "взят",
  called: "позвонил",
  qualified: "квалифицирован",
  unqualified: "не квалифицирован",
  in_bitrix: "отдали в Bitrix",
  v_otpuske: "в отпуске",
  avtootvet: "автоответ",
  not_interested: "не интересно",
  closed: "закрыт",
};

export function Leads({ mine = false }: { mine?: boolean }) {
  const { principal } = useAuth();
  const isManager = principal?.role === "manager";
  const qc = useQueryClient();
  const toast = useToast();
  const [status, setStatus] = useState("");
  const [replyKind, setReplyKind] = useState("");
  // Направление (владелец 20.08: «в ленте лидов ещё возможность выбрать ответы
  // по направлениям тоже надо»). Считается по ящику, который вёл переписку.
  const [napravlenie, setNapravlenie] = useState("");
  // пейджер: лента лидов растёт вместе с базой, 500 без листания не хватит
  const [offset, setOffset] = useState(0);
  const PAGE = 100;

  const filter = {
    status: status || undefined,
    reply_kind: replyKind || undefined,
    napravlenie: napravlenie || undefined,
    assigned_to: mine && principal ? principal.user_id : undefined,
    unassigned: !mine && !status ? undefined : undefined,
    limit: PAGE,
    offset,
  };

  const q = useQuery({
    queryKey: ["leads", filter],
    queryFn: () => api.leads(filter),
    refetchInterval: 15_000, // поллинг вместо WebSocket: гасит взятые у всех
  });
  useEffect(() => { setOffset(0); }, [status, replyKind, napravlenie, mine]);

  const take = useMutation({
    mutationFn: (id: number) => api.takeLead(id),
    onSuccess: (res) => {
      toast("success", `Лид #${res.lead.id} — ваш`);
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
    onError: (e) => {
      // 409 (истинная гонка) и 400 (уже taken) — оба «взял другой»
      if (e instanceof ApiError && (e.status === 409 || e.status === 400)) {
        toast("error", "Уже взял другой менеджер");
        qc.invalidateQueries({ queryKey: ["leads"] });
      } else {
        toast("error", e instanceof ApiError ? e.detail : "Ошибка");
      }
    },
  });

  // Крестик «не интересно» (владелец 11.08: «чтобы не висели неактуальные
  // лиды»). Не удаление: лид уходит с ленты, но достаётся фильтром по статусу
  // и возвращается в работу — промах по крестику не должен быть необратимым.
  const perevesti = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      api.setLeadStatus(id, status),
    onSuccess: (res) => {
      const имя = ПОДПИСЬ[res.lead.status] || res.lead.status;
      toast("success", `Лид #${res.lead.id} → «${имя}»`);
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : "Ошибка"),
  });

  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  const leads = q.data?.leads ?? [];
  // Скрытые из ленты: «не интересно» и убранные. Владелец 20.08: «почему у
  // всех статус новый? хотя я несколько перевёл в не интересно» — переводы
  // срабатывали, но лид ПРОПАДАЛ из ленты молча, и выглядело это как будто
  // статус не сохранился. Теперь видно, сколько спрятано и где их искать.
  // stats типизирован как Record<string, unknown>, поэтому берём через as:
  // без этого обращение к by_status — ошибка типов (сборка её не ловит,
  // но полагаться на отсутствие проверки не стоит).
  const поСтатусам = (((q.data?.stats as any) || {}).by_status || {}) as
    Record<string, number>;
  const скрытоНеинтересно = поСтатусам["not_interested"] || 0;
  // «Отдали в Bitrix» лента тоже прячет: лид ушёл в отдел продаж. Счётчик
  // рядом — чтобы спрятанное не выглядело пропажей (владелец 24.08).
  const скрытоBitrix = поСтатусам["in_bitrix"] || 0;

  return (
    <div>
      <div className="page-head">
        <h1>{mine ? "Мои лиды" : "Лента лидов"}</h1>
        <div className="muted">
          {leads.length} шт.
          {!mine && !status && скрытоНеинтересно > 0 && (
            <>
              {" · "}
              <button className="btn-link" title="показать их"
                      onClick={() => setStatus("not_interested")}>
                скрыто «не интересно»: {скрытоНеинтересно}
              </button>
            </>
          )}
          {!mine && !status && скрытоBitrix > 0 && (
            <>
              {" · "}
              <button className="btn-link" title="показать их"
                      onClick={() => setStatus("in_bitrix")}>
                отдали в Bitrix: {скрытоBitrix}
              </button>
            </>
          )}
        </div>
      </div>

      {!mine && (
        <div className="filterbar">
          <label>Статус
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              {STATUSES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </label>
          <label>Приоритет
            <select value={replyKind} onChange={(e) => setReplyKind(e.target.value)}>
              {REPLY_KINDS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </label>
          <label>Направление
            <select value={napravlenie}
                    onChange={(e) => setNapravlenie(e.target.value)}>
              <option value="">оба</option>
              <option value="kc">Компрессор Центр</option>
              <option value="meyer">Meyer</option>
            </select>
          </label>
        </div>
      )}

      {leads.length === 0 ? (
        <Empty hint="Тёплые ответы появятся здесь после ответов на рассылку" />
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Компания (ИНН)</th><th>Контакт</th><th>Потребность</th>
                <th title="Автоответ назвал другой адрес — копия письма на него и что с ней стало">
                  Копия на адрес
                </th>
                <th>Приоритет</th>
                <th title="Открытия по трекинг-пикселю. В РФ приблизительно: Mail.ru/Яндекс проксируют картинки (накрутка/недоучёт). Решения — по ответу/клику.">
                  Открыл ✉
                </th>
                <th title="наш последний ответ этой компании">Ответ</th>
                <th>Без движения</th><th>Статус</th><th></th>
              </tr>
            </thead>
            <tbody>
              {leads.map((l) => <LeadRow key={l.id} lead={l} isManager={isManager}
                                         onTake={() => take.mutate(l.id)} taking={take.isPending}
                                         onMove={(s) => perevesti.mutate({ id: l.id, status: s })}
                                         moving={perevesti.isPending} />)}
            </tbody>
          </table>
        </div>
      )}
      <Pager offset={offset} shown={leads.length} unit="лидов"
        onPrev={() => setOffset(Math.max(0, offset - PAGE))}
        onNext={() => setOffset(offset + PAGE)} />
    </div>
  );
}

// Время ответа коротко: сегодняшний — часами, прежний — датой. Оператору важно
// «отвечали ли и когда», а не секунда отправки.
function когда(ts?: string | null): string {
  if (!ts) return "";
  const d = new Date(ts);
  if (isNaN(d.getTime())) return String(ts).slice(0, 16).replace("T", " ");
  const сегодня = new Date();
  const тот_же_день = d.toDateString() === сегодня.toDateString();
  return тот_же_день
    ? d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
}

function LeadRow({ lead, isManager, onTake, taking, onMove, moving }: {
  lead: Lead; isManager: boolean; onTake: () => void; taking: boolean;
  onMove: (status: string) => void; moving: boolean;
}) {
  const rb = replyBadge(lead.reply_kind);
  const age = ageHours(lead.created_at);
  const ageCls = age === null ? "" : age > 4 ? "age-red" : age > 2 ? "age-yellow" : "";
  // менеджер видит контакт маскированным до «Взять» (его лид — открыт)
  const masked = isManager && lead.assigned_to == null;
  const suppressed = lead.status === "unsub_request" || lead.reply_kind === "unsub_request";
  return (
    <tr className={rb.cls === "hot" ? "row-hot" : ""}>
      <td>
        <Link to={`/leads/${lead.id}`}>{lead.company_name || "—"}</Link>
        <div className="muted small">{lead.inn || ""}</div>
      </td>
      <td>
        {masked ? maskEmail(lead.email) : lead.email}
        <div className="muted small">{masked ? maskPhone(lead.phone) : (lead.phone || "")}</div>
      </td>
      <td className="need">{lead.need ? `«${lead.need.slice(0, 80)}»` : "—"}</td>
      {/* Копия по автоответу: адрес + ЖИВОЙ статус (владелец 20.08 — «не
          понятно, на копию письма мы написали такое же письмо или нет»).
          Раньше это было текстом внутри «Потребности» и замерзало на
          «поставлена в очередь», даже когда копию давно пропустили. */}
      <td className="kopiya">
        {lead.kopiya && lead.kopiya.length > 0 ? lead.kopiya.map((k, i) => (
          <div key={i} className="kopiya-strochka">
            <span className="kopiya-adres">{k.email}</span>{" "}
            <span className={"kopiya-status kopiya-" + k.status}>
              {k.chelovecheski || k.status}
            </span>
          </div>
        )) : <span className="muted">—</span>}
      </td>
      <td><span className={`reply reply-${rb.cls}`}>{rb.icon} {rb.label}</span></td>
      <td className="muted" title="в РФ приблизительно (прокси картинок)">
        {lead.opens ? `✉${lead.opens}` : "—"}
      </td>
      <td className="otvet">
        {lead.otvet
          ? <span className="reply reply-ok" title={`${lead.otvet.subject || ""}\n${lead.otvet.ts || ""}`}>
              ↩ {когда(lead.otvet.ts)}
            </span>
          : <span className="muted">—</span>}
      </td>
      <td className={ageCls}>{age === null ? "—" : `${age.toFixed(1)} ч`}</td>
      <td>
        <StatusBadge status={lead.status} />
        {suppressed && <div className="danger small">отписался — звонить нельзя</div>}
      </td>
      <td>
        {lead.assigned_to == null
          ? <button className="btn btn-take" onClick={onTake} disabled={taking}>Взять</button>
          : <span className="muted small">взят</span>}
        {(ПЕРЕХОДЫ[lead.status] || []).length > 0 && (
          <select className="lead-move" value="" disabled={moving}
                  title="перевести лид в другой статус; из ленты он уйдёт, но найдётся фильтром по статусу"
                  onChange={(e) => { const s = e.target.value; e.target.value = "";
                                     if (s) onMove(s); }}>
            <option value="">→ перевести</option>
            {(ПЕРЕХОДЫ[lead.status] || []).map((s) => (
              <option key={s} value={s}>{ПОДПИСЬ[s] || s}</option>
            ))}
          </select>
        )}
      </td>
    </tr>
  );
}
