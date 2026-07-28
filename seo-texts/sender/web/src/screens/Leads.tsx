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

const REPLY_KINDS = ["", "hot", "interested", "auto_reply", "not_interested"];
const STATUSES = ["", "new", "taken", "called", "qualified", "not_qualified", "in_bitrix"];

export function Leads({ mine = false }: { mine?: boolean }) {
  const { principal } = useAuth();
  const isManager = principal?.role === "manager";
  const qc = useQueryClient();
  const toast = useToast();
  const [status, setStatus] = useState("");
  const [replyKind, setReplyKind] = useState("");
  // пейджер: лента лидов растёт вместе с базой, 500 без листания не хватит
  const [offset, setOffset] = useState(0);
  const PAGE = 100;

  const filter = {
    status: status || undefined,
    reply_kind: replyKind || undefined,
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
  useEffect(() => { setOffset(0); }, [status, replyKind, mine]);

  // чистка ленты от тестовых/мусорных лидов (владелец 28.07). Мягко: лид
  // получает статус deleted и пропадает из ленты, строка остаётся в базе —
  // ошибочное удаление возвращается через API restore.
  const убрать = useMutation({
    mutationFn: (id: number) => api.deleteLead(id, "мусор/тест"),
    onSuccess: () => {
      toast("success", "Лид убран из ленты");
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : "Ошибка"),
  });

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

  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  const leads = q.data?.leads ?? [];

  return (
    <div>
      <div className="page-head">
        <h1>{mine ? "Мои лиды" : "Лента лидов"}</h1>
        <div className="muted">{leads.length} шт.</div>
      </div>

      {!mine && (
        <div className="filterbar">
          <label>Статус
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              {STATUSES.map((s) => <option key={s} value={s}>{s || "все"}</option>)}
            </select>
          </label>
          <label>Приоритет
            <select value={replyKind} onChange={(e) => setReplyKind(e.target.value)}>
              {REPLY_KINDS.map((s) => <option key={s} value={s}>{s || "все"}</option>)}
            </select>
          </label>
        </div>
      )}

      {leads.length === 0 ? (
        <Empty hint="Тёплые ответы появятся здесь после ответов на рассылку" />
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Компания (ИНН)</th><th>Контакт</th><th>Потребность</th>
              <th>Приоритет</th>
              <th title="Открытия по трекинг-пикселю. В РФ приблизительно: Mail.ru/Яндекс проксируют картинки (накрутка/недоучёт). Решения — по ответу/клику.">
                Открыл ✉
              </th>
              <th>Без движения</th><th>Статус</th><th></th>
            </tr>
          </thead>
          <tbody>
            {leads.map((l) => <LeadRow key={l.id} lead={l} isManager={isManager}
                                       onTake={() => take.mutate(l.id)} taking={take.isPending}
                                       onDelete={isManager ? undefined : () => {
                                         if (confirm(`Убрать лид ${l.company_name || l.email} из ленты?`))
                                           убрать.mutate(l.id);
                                       }} />)}
          </tbody>
        </table>
      )}
      <Pager offset={offset} shown={leads.length} unit="лидов"
        onPrev={() => setOffset(Math.max(0, offset - PAGE))}
        onNext={() => setOffset(offset + PAGE)} />
    </div>
  );
}

function LeadRow({ lead, isManager, onTake, taking, onDelete }: {
  lead: Lead; isManager: boolean; onTake: () => void; taking: boolean;
  onDelete?: () => void;
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
      <td><span className={`reply reply-${rb.cls}`}>{rb.icon} {rb.label}</span></td>
      <td className="muted" title="в РФ приблизительно (прокси картинок)">
        {lead.opens ? `✉${lead.opens}` : "—"}
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
        {onDelete && (
          <button className="btn btn-ghost btn-sm danger" title="убрать из ленты (тест/мусор)"
            onClick={onDelete}>×</button>
        )}
      </td>
    </tr>
  );
}
