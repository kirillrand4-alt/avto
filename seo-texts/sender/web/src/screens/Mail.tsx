// Экран «Почта» — read-only IMAP-браузер по любому из ящиков панели.
// Выбор ящика + папки (Входящие/Отправленные/…), список ВСЕХ писем (не только
// непрочитанных), чтение письма и цепочки. Поиск по адресу/теме. Ничего не
// отправляет и не удаляет — только просмотр (холд соблюдён).

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Spinner, ErrorBox, Empty } from "../components/ui";
import type { MailMsg } from "../api/types";

const ROLE_RU: Record<string, string> = {
  inbox: "Входящие", sent: "Отправленные", junk: "Спам",
  drafts: "Черновики", trash: "Корзина", other: "Папка",
};

export function Mail() {
  const [mb, setMb] = useState<string>("");
  const [folder, setFolder] = useState<string>("INBOX");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [openUid, setOpenUid] = useState<string | null>(null);
  const [showThread, setShowThread] = useState(false);

  const boxes = useQuery({ queryKey: ["mail-boxes"], queryFn: api.mailMailboxes });
  const activeMb = mb || boxes.data?.mailboxes?.[0]?.mailbox_id || "";

  const folders = useQuery({
    queryKey: ["mail-folders", activeMb],
    queryFn: () => api.mailFolders(activeMb),
    enabled: !!activeMb,
  });

  const msgs = useQuery({
    queryKey: ["mail-msgs", activeMb, folder, query],
    queryFn: () => api.mailMessages(activeMb, { folder, limit: 100, search: query || undefined }),
    enabled: !!activeMb,
  });

  const opened = useQuery({
    queryKey: ["mail-open", activeMb, folder, openUid],
    queryFn: () => api.mailMessage(activeMb, folder, openUid!),
    enabled: !!activeMb && !!openUid,
  });

  const thread = useQuery({
    queryKey: ["mail-thread", activeMb, folder, openUid],
    queryFn: () => api.mailThread(activeMb, folder, openUid!),
    enabled: !!activeMb && !!openUid && showThread,
  });

  if (boxes.isLoading) return <Spinner />;
  if (boxes.error) return <ErrorBox error={boxes.error} />;

  return (
    <div className="mail-screen">
      <h1>Почта</h1>
      <div className="mail-toolbar" style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        <select value={activeMb} onChange={(e) => { setMb(e.target.value); setOpenUid(null); }}>
          {boxes.data!.mailboxes.map((b) => (
            <option key={b.mailbox_id} value={b.mailbox_id}>
              {b.mailbox_id} · {b.from_name}
            </option>
          ))}
        </select>
        <select value={folder} onChange={(e) => { setFolder(e.target.value); setOpenUid(null); }}>
          {(folders.data?.folders || [{ name: "INBOX", role: "inbox" }]).map((f) => (
            <option key={f.name} value={f.name}>
              {ROLE_RU[f.role] || f.name}{f.role === "other" ? ` (${f.name})` : ""}
            </option>
          ))}
        </select>
        <form onSubmit={(e) => { e.preventDefault(); setQuery(search); setOpenUid(null); }} style={{ display: "flex", gap: 4 }}>
          <input placeholder="поиск: адрес или тема" value={search}
                 onChange={(e) => setSearch(e.target.value)} />
          <button className="btn" type="submit">Найти</button>
          {query && <button className="btn" type="button" onClick={() => { setSearch(""); setQuery(""); }}>Сброс</button>}
        </form>
      </div>

      <div className="mail-body" style={{ display: "grid", gridTemplateColumns: openUid ? "minmax(280px,1fr) 2fr" : "1fr", gap: 12 }}>
        {/* список писем */}
        <div className="mail-list card" style={{ maxHeight: "70vh", overflow: "auto" }}>
          {msgs.isLoading && <Spinner />}
          {msgs.error && <ErrorBox error={msgs.error} />}
          {msgs.data && msgs.data.total === 0 && <Empty hint="Писем нет" />}
          {msgs.data && (
            <>
              <div className="muted" style={{ padding: "4px 8px" }}>всего: {msgs.data.total}</div>
              {msgs.data.messages.map((m: MailMsg) => (
                <div key={m.uid}
                     onClick={() => { setOpenUid(m.uid); setShowThread(false); }}
                     className={`mail-row ${openUid === m.uid ? "active" : ""}`}
                     style={{ padding: "8px 10px", borderTop: "1px solid var(--border,#2a2a2a)", cursor: "pointer", fontWeight: m.seen ? "normal" : 600 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <span>{folder.toLowerCase().includes("sent") || folder === "Отправленные" ? `→ ${m.to_addr}` : (m.from_name || m.from_addr)}</span>
                    <span className="muted" style={{ fontSize: 12, whiteSpace: "nowrap" }}>{m.date_iso ? m.date_iso.slice(0, 16).replace("T", " ") : m.date}</span>
                  </div>
                  <div className="muted" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {!m.seen && <span style={{ color: "#3b82f6" }}>● </span>}{m.subject || "(без темы)"}
                  </div>
                </div>
              ))}
            </>
          )}
        </div>

        {/* открытое письмо + цепочка */}
        {openUid && (
          <div className="mail-view card" style={{ padding: 12, maxHeight: "70vh", overflow: "auto" }}>
            {opened.isLoading && <Spinner />}
            {opened.error && <ErrorBox error={opened.error} />}
            {opened.data && (
              <>
                <div style={{ marginBottom: 8 }}>
                  <div><b>{opened.data.subject || "(без темы)"}</b></div>
                  <div className="muted">От: {opened.data.from_name} &lt;{opened.data.from_addr}&gt;</div>
                  <div className="muted">Кому: {opened.data.to_addr} · {opened.data.date}</div>
                </div>
                <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit" }}>{opened.data.body || "(пустое тело)"}</pre>
                <button className="btn" style={{ marginTop: 10 }}
                        onClick={() => setShowThread((v) => !v)}>
                  {showThread ? "Скрыть цепочку" : "Показать всю цепочку"}
                </button>
                {showThread && (
                  <div style={{ marginTop: 10, borderTop: "1px solid var(--border,#2a2a2a)", paddingTop: 10 }}>
                    {thread.isLoading && <Spinner />}
                    {thread.data && thread.data.thread.map((t) => (
                      <div key={t.uid} style={{ borderTop: "1px dashed var(--border,#2a2a2a)", padding: "8px 0" }}>
                        <div className="muted" style={{ fontSize: 12 }}>
                          {t.from_addr} → {t.to_addr} · {t.date}
                        </div>
                        <div><b>{t.subject}</b></div>
                        <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", margin: 0 }}>{t.body || t.subject}</pre>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
      <p className="muted" style={{ marginTop: 10, fontSize: 12 }}>
        Просмотр только для чтения — письма не помечаются прочитанными, не удаляются и не отправляются.
      </p>
    </div>
  );
}
