// Экран «Почта»: чтение входящих и исходящих любого ящика панели.
//
// Восстановлен 26.07.2026. Бэкенд (sender/mailbrowser.py + ручки /mail/*) и
// методы клиента были на месте, а сам экран отсутствовал: исходников нового
// фронта в репозитории не было, и в бандл он не попал. Владелец: «была панелька
// где я мог входящие и исходящие любого ящика посмотреть, сейчас пропала».
//
// Только чтение: IMAP открывается на просмотр, ничего не помечается и не
// удаляется. Тред подтягивается по кнопке — лишний обход IMAP на каждое письмо
// не нужен.

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { MailFull, MailMsg } from "../api/types";
import { Card, Empty, ErrorBox, Spinner } from "../components/ui";

const PAGE = 50;

/** Роли папок с сервера -> человеческие названия. */
const FOLDER_RU: Record<string, string> = {
  inbox: "Входящие",
  sent: "Отправленные",
  spam: "Спам",
  trash: "Корзина",
  drafts: "Черновики",
};

function folderLabel(name: string, role?: string): string {
  if (role && FOLDER_RU[role]) return FOLDER_RU[role];
  const low = (name || "").toLowerCase();
  if (low === "inbox") return "Входящие";
  if (low.includes("sent") || low.includes("отправ")) return "Отправленные";
  if (low.includes("spam") || low.includes("junk")) return "Спам";
  return name;
}

function when(m: MailMsg): string {
  // date_iso пустой, если дату письма разобрать не удалось — тогда показываем,
  // что прислал сервер, а не «Invalid Date».
  if (!m.date_iso) return m.date || "";
  const d = new Date(m.date_iso);
  return Number.isNaN(d.getTime())
    ? (m.date || "")
    : d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit",
                                  year: "2-digit", hour: "2-digit",
                                  minute: "2-digit" });
}

export function Mail() {
  const [mailbox, setMailbox] = useState("");
  const [folder, setFolder] = useState("INBOX");
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<{ uid: string } | null>(null);
  const [thread, setThread] = useState(false);

  const boxes = useQuery({
    queryKey: ["mail-boxes"],
    queryFn: () => api.mailMailboxes(),
  });

  // первый ящик подставляем сами: пустой экран без выбора выглядит поломкой
  useEffect(() => {
    const list = boxes.data?.mailboxes || [];
    if (!mailbox && list.length) setMailbox(list[0].mailbox_id);
  }, [boxes.data, mailbox]);

  const folders = useQuery({
    queryKey: ["mail-folders", mailbox],
    queryFn: () => api.mailFolders(mailbox),
    enabled: !!mailbox,
  });

  // #58: у каждого провайдера папки называются по-своему («Sent» у Яндекса,
  // «&BB4...» у mail.ru). При смене ящика прошлое имя папки не существует —
  // запрос падал «папка 'Sent' недоступна» при выбранных «Входящих».
  // Как только пришёл список папок нового ящика, проверяем выбор и при
  // несовпадении откатываемся на INBOX.
  useEffect(() => {
    const list = folders.data?.folders;
    if (!list || !list.length) return;
    if (!list.some((f) => f.name === folder)) {
      const inbox = list.find((f) => f.role === "inbox") || list[0];
      setFolder(inbox.name);
      setPage(0);
      setOpen(null);
    }
  }, [folders.data, folder]);

  const msgs = useQuery({
    queryKey: ["mail-msgs", mailbox, folder, page, query],
    queryFn: () => api.mailMessages(mailbox, {
      folder, limit: PAGE, offset: page * PAGE,
      search: query || undefined,
    }),
    enabled: !!mailbox && !!folder,
  });

  const msg = useQuery({
    queryKey: ["mail-msg", mailbox, folder, open?.uid],
    queryFn: () => api.mailMessage(mailbox, folder, open!.uid),
    enabled: !!open?.uid,
  });

  const chain = useQuery({
    queryKey: ["mail-thread", mailbox, folder, open?.uid],
    queryFn: () => api.mailThread(mailbox, folder, open!.uid),
    enabled: !!open?.uid && thread,
  });

  const list = msgs.data?.messages || [];
  const total = msgs.data?.total || 0;
  const pages = Math.max(1, Math.ceil(total / PAGE));

  return (
    <div>
      <div className="screen-head">
        <h1>Почта</h1>
        <div className="muted">чтение ящиков панели — входящие и отправленные</div>
      </div>

      <div className="toolbar">
        <label className="field">
          ящик
          <select value={mailbox}
                  onChange={(e) => { setMailbox(e.target.value); setFolder("INBOX");
                                     setPage(0); setOpen(null); }}>
            {(boxes.data?.mailboxes || []).map((b) => (
              <option key={b.mailbox_id} value={b.mailbox_id}>
                {b.from_name ? `${b.from_name} — ` : ""}{b.mailbox_id}
                {b.division ? ` (${b.division})` : ""}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          папка
          <select value={folder}
                  onChange={(e) => { setFolder(e.target.value); setPage(0); setOpen(null); }}>
            {(folders.data?.folders || [{ name: "INBOX", role: "inbox" }]).map((f) => (
              <option key={f.name} value={f.name}>
                {folderLabel(("title" in f && f.title) || f.name, f.role)}
              </option>
            ))}
          </select>
        </label>
        <label className="field grow">
          поиск
          <input className="search-input" value={search} placeholder="тема или адрес"
                 onChange={(e) => setSearch(e.target.value)}
                 onKeyDown={(e) => {
                   if (e.key === "Enter") { setQuery(search.trim()); setPage(0); }
                 }} />
        </label>
        <button className="btn" onClick={() => { setQuery(search.trim()); setPage(0); }}>
          Искать
        </button>
        {query && (
          <button className="btn btn-ghost"
                  onClick={() => { setSearch(""); setQuery(""); setPage(0); }}>
            Сбросить
          </button>
        )}
      </div>

      {boxes.error && <ErrorBox error={boxes.error} />}
      {folders.error && <ErrorBox error={folders.error} />}
      {msgs.error && <ErrorBox error={msgs.error} />}

      {msgs.isLoading ? <Spinner /> : list.length === 0 ? (
        <Empty hint={query ? "По запросу ничего не нашлось." : "В этой папке писем нет."} />
      ) : (
        <div className="table-wrap">
          <table className="data-table dense">
            <thead>
              <tr>
                <th>Когда</th><th>От кого</th><th>Кому</th><th>Тема</th>
              </tr>
            </thead>
            <tbody>
              {list.map((m) => (
                <tr key={m.uid}
                    onClick={() => { setOpen({ uid: m.uid }); setThread(false); }}
                    style={{ cursor: "pointer",
                             fontWeight: m.seen ? undefined : "var(--fw-semibold)" }}
                    className={open?.uid === m.uid ? "row-selected" : undefined}>
                  <td className="nowrap">{when(m)}</td>
                  <td>{m.from_name || m.from_addr}
                    {m.from_name && <div className="muted small">{m.from_addr}</div>}</td>
                  <td className="muted">{m.to_addr}</td>
                  <td>{m.subject || <span className="muted">без темы</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="pager">
            <button className="btn btn-sm" disabled={page === 0}
                    onClick={() => setPage((x) => Math.max(0, x - 1))}>←</button>
            <span className="grow">
              письма {page * PAGE + 1}-{Math.min((page + 1) * PAGE, total)} из {total}
              {" · "}страница {page + 1} из {pages}
            </span>
            <button className="btn btn-sm" disabled={page + 1 >= pages}
                    onClick={() => setPage((x) => x + 1)}>→</button>
          </div>
        </div>
      )}

      {open && (
        <Card title={msg.data?.subject || "Письмо"}>
          {msg.isLoading ? <Spinner /> : msg.error ? <ErrorBox error={msg.error} /> : msg.data ? (
            <>
              <div className="kv-list">
                <div className="kv-row">
                  <span className="kv-key">от кого</span>
                  <span className="kv-val">
                    {msg.data.from_name} <span className="muted">{msg.data.from_addr}</span>
                  </span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">кому</span>
                  <span className="kv-val">{msg.data.to_addr}</span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">когда</span>
                  <span className="kv-val">{when(msg.data)}</span>
                </div>
              </div>
              <pre className="confirm-letter">{msg.data.body}</pre>
              <div className="actions">
                <button className="btn" onClick={() => setThread((t) => !t)}>
                  {thread ? "Скрыть переписку" : "Показать всю переписку"}
                </button>
                <button className="btn btn-ghost" onClick={() => setOpen(null)}>Закрыть</button>
              </div>
              {thread && (
                chain.isLoading ? <Spinner /> : chain.error ? <ErrorBox error={chain.error} /> : (
                  <div className="mail-thread">
                    {(chain.data?.thread || []).map((t: MailFull, i: number) => (
                      <div key={i} className="mail-thread-item">
                        <div className="muted small">
                          {when(t)} · {t.from_name || t.from_addr} → {t.to_addr}
                        </div>
                        <div><b>{t.subject}</b></div>
                        <pre className="confirm-letter">{t.body}</pre>
                      </div>
                    ))}
                  </div>
                )
              )}
            </>
          ) : null}
        </Card>
      )}
    </div>
  );
}
