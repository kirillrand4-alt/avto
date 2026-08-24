# -*- coding: utf-8 -*-
"""Почему ответ показывается в ленте дважды: два показа или две отправки.

Владелец 24.08 прислал экран: в переписке с «Урзпм» его ответ виден два
раза подряд, второй помечен «reply_sent · 10:08 · ural.prommetiz@bk.ru ·
sent». Вопрос не косметический: одно дело лишняя строка на экране, другое
— письмо, ушедшее клиенту дважды.

Разводим это фактом. Ручной ответ оставляет след в двух местах сразу:
карточкой в очереди подтверждения (kind=reply) и письмом в очереди
сообщений. Если запись одна в каждом — виновата отрисовка. Если в
messages две строки со статусом sent или два события reply_sent — ушло
дважды, и это уже к получателю.
"""
import sqlite3

АДРЕС = "ural.prommetiz@bk.ru"
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

ряд = c.execute("SELECT id, company_name, inn FROM recipients WHERE email=?",
                (АДРЕС,)).fetchone()
if not ряд:
    print("получателя с адресом %s нет" % АДРЕС)
    raise SystemExit(0)
пол = ряд["id"]
print("получатель #%s — %s (ИНН %s)"
      % (пол, str(ряд["company_name"] or "")[:44], ряд["inn"]))

print("\n=== ПИСЬМА ЭТОМУ ПОЛУЧАТЕЛЮ ===")
for р in c.execute(
        "SELECT id, status, mailbox_id, sent_at, created_at, subject, "
        "       rfc_message_id, in_reply_to, thread_id, "
        "       length(body_rendered) длина "
        "  FROM messages WHERE recipient_id=? ORDER BY id", (пол,)):
    print("  #%-6s %-14s %s | ящик %s"
          % (р["id"], р["status"], str(р["sent_at"] or "не отправлено")[:16],
             str(р["mailbox_id"] or "?")[:34]))
    print("        тема: %s" % str(р["subject"] or "")[:60])
    print("        тело %s зн. | rfc=%s | тред=%s"
          % (р["длина"], str(р["rfc_message_id"] or "—")[:36],
             str(р["thread_id"] or "—")[:26]))

print("\n=== КАРТОЧКИ ОЧЕРЕДИ ===")
кол = {с[1] for с in c.execute("PRAGMA table_info(confirm_reviews)")}
поля = [п for п in ("id", "status", "kind", "created_at", "subject",
                    "message_id", "reason") if п in кол]
for р in c.execute("SELECT %s FROM confirm_reviews WHERE recipient_id=? "
                   "ORDER BY id" % ", ".join(поля), (пол,)):
    print("  " + " | ".join("%s=%s" % (п, str(р[п])[:40]) for п in поля
                            if р[п] not in (None, "")))

print("\n=== СОБЫТИЯ ===")
for р in c.execute(
        "SELECT id, event_type, event_ts, mailbox_id, message_id, dedup_key "
        "  FROM events WHERE recipient_id=? ORDER BY id", (пол,)):
    print("  [%-12s] %s | письмо %s | ящик %s"
          % (р["event_type"], str(р["event_ts"])[:19],
             р["message_id"], str(р["mailbox_id"] or "?")[:30]))
    print("        ключ дедупа: %s" % str(р["dedup_key"] or "—")[:70])

print("\n=== СВОДКА ===")
отпр = c.execute("SELECT COUNT(*) FROM messages WHERE recipient_id=? "
                 "AND status='sent'", (пол,)).fetchone()[0]
соб = c.execute("SELECT COUNT(*) FROM events WHERE recipient_id=? "
                "AND event_type IN ('sent','reply_sent')", (пол,)).fetchone()[0]
карт = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE recipient_id=?",
                 (пол,)).fetchone()[0]
print("  писем со статусом sent: %d" % отпр)
print("  событий отправки:       %d" % соб)
print("  карточек в очереди:     %d" % карт)
print("\n  вывод: %s"
      % ("письмо ушло ОДИН раз — дублируется показ"
         if отпр <= 2 and соб <= 2 else
         "похоже на ПОВТОРНУЮ отправку, надо смотреть тела"))
