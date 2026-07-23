// Экран «Написать письмо» — ручная отправка ОДНОГО письма владельцем.
// Отправка РЕАЛЬНАЯ (SMTP, минуя dry_run-холд массовой рассылки): путь одиночный,
// комплаенс (suppression + байлайн + футер отписки) применяет бэкенд.

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { useToast } from "../components/Toast";
import { Spinner, ErrorBox, Card } from "../components/ui";

export function Compose() {
  const toast = useToast();
  const [toEmail, setToEmail] = useState("");
  const [subject, setSubject] = useState("");
  const [text, setText] = useState("");
  const [mailbox, setMailbox] = useState("");
  const [lastSent, setLastSent] = useState<string | null>(null);

  const mbq = useQuery({
    queryKey: ["mailboxes-readiness"],
    queryFn: () => api.mailboxesReadiness(),
  });

  const send = useMutation({
    mutationFn: () => api.sendManual({
      to_email: toEmail.trim(), subject: subject.trim(), text: text.trim(),
      mailbox_id: mailbox || undefined,
    }),
    onSuccess: (r) => {
      if (r.dry_run) {
        toast("error", "Письмо собрано, но SMTP не вызван (dry_run) — сообщите Claude");
      } else {
        toast("success", `Отправлено на ${r.to_email} с ящика ${r.mailbox_id}`);
        setLastSent(`${r.to_email} (${r.sent_message_id || "без Message-ID"})`);
        setToEmail(""); setSubject(""); setText("");
      }
    },
    onError: (e) => toast("error", e instanceof ApiError ? e.detail : "Ошибка отправки"),
  });

  if (mbq.isLoading) return <Spinner />;
  if (mbq.error) return <ErrorBox error={mbq.error} />;
  const mailboxes = mbq.data?.mailboxes ?? [];
  const canSend = toEmail.trim().includes("@") && subject.trim() && text.trim() && !send.isPending;

  return (
    <div className="compose">
      <div className="page-head"><h1>Написать письмо</h1></div>

      <Card title="Ручная отправка (реальная)">
        <p className="muted small">
          Письмо уйдёт ПО-НАСТОЯЩЕМУ выбранным ящиком, вне кампаний и вне холда массовой
          рассылки. Байлайн «ООО «Руспром»» и футер отписки добавятся автоматически.
          Отписавшимся и адресам из suppression отправка заблокирована.
        </p>
        <div className="reply-box">
          <select value={mailbox} onChange={(e) => setMailbox(e.target.value)}>
            <option value="">Ящик: первый настроенный</option>
            {mailboxes.map((m) => (
              <option key={m.mailbox_id} value={m.mailbox_id}>
                {m.mailbox_id}{m.paused ? " (на паузе)" : ""} · сегодня {m.sent_today}/{m.daily_limit}
              </option>
            ))}
          </select>
          <input className="reply-subject" placeholder="Кому (email)"
                 value={toEmail} onChange={(e) => setToEmail(e.target.value)} />
          <input className="reply-subject" placeholder="Тема"
                 value={subject} onChange={(e) => setSubject(e.target.value)} />
          <textarea className="reply-text" rows={10}
                    placeholder="Текст письма. Подпись-байлайн и футер отписки добавятся сами."
                    value={text} onChange={(e) => setText(e.target.value)} />
          <div className="actions">
            <button className="btn btn-primary" disabled={!canSend}
                    onClick={() => send.mutate()}>
              {send.isPending ? "Отправка…" : "Отправить по-настоящему"}
            </button>
            {lastSent && <span className="muted small">Последнее отправлено: {lastSent}</span>}
          </div>
        </div>
      </Card>
    </div>
  );
}
