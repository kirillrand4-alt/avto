# -*- coding: utf-8 -*-
"""Ушёл ли ручной ответ «Сталь Технологиям» про дилерство BERG.

Владелец написал ответ на отказ «у нас компресорры Берг стоят, КИТАЙ НЕ
ИНТЕРЕСЕН СОВСЕМ» — разворот на то, что «Компрессор Центр» официальный
дилер BERG. Спрашивает, ушло письмо или нет.

Ищем по трём следам сразу, потому что ручной ответ может лежать в любом
из них: письмо в messages, карточка в очереди подтверждения, событие
отправки. И отдельно — по слову BERG во всей исходящей почте за сегодня,
на случай если оно ушло не тому получателю, которого мы ждём.
"""
import sqlite3
import time

ПОЛУЧАТЕЛЬ = 2998
АДРЕС = "com@sttehnol.ru"
СЕГОДНЯ = time.strftime("%Y-%m-%d")

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("=== ПИСЬМА ЭТОМУ ПОЛУЧАТЕЛЮ ===")
for р in c.execute(
        "SELECT id, status, mailbox_id, scheduled_at, sent_at, subject, "
        "       length(body_rendered) длина, last_error, created_at "
        "  FROM messages WHERE recipient_id=? ORDER BY id DESC LIMIT 10",
        (ПОЛУЧАТЕЛЬ,)):
    print("  #%-6s %-14s %s" % (р["id"], р["status"],
                                str(р["subject"] or "")[:52]))
    print("        создано %s | срок %s | отправлено %s | ящик %s | тело %s зн."
          % (str(р["created_at"])[:16], str(р["scheduled_at"])[:16],
             str(р["sent_at"] or "—")[:16],
             str(р["mailbox_id"] or "не назначен")[:32], р["длина"]))
    if р["last_error"]:
        print("        ошибка: %s" % str(р["last_error"])[:110])

print("\n=== КАРТОЧКИ ОЧЕРЕДИ ПОДТВЕРЖДЕНИЯ ===")
кол = {с[1] for с in c.execute("PRAGMA table_info(confirm_reviews)")}
поля = [п for п in ("id", "status", "created_at", "subject", "reason",
                    "kind", "message_id") if п in кол]
for р in c.execute("SELECT %s FROM confirm_reviews WHERE recipient_id=? "
                   "ORDER BY id DESC LIMIT 8" % ", ".join(поля),
                   (ПОЛУЧАТЕЛЬ,)):
    print("  " + " | ".join("%s=%s" % (п, str(р[п])[:44]) for п in поля
                            if р[п] not in (None, "")))

print("\n=== СОБЫТИЯ ПО ЭТОМУ ПОЛУЧАТЕЛЮ ЗА СЕГОДНЯ ===")
for р in c.execute(
        "SELECT id, event_type, event_ts, mailbox_id FROM events "
        " WHERE recipient_id=? AND substr(event_ts,1,10)=? ORDER BY id",
        (ПОЛУЧАТЕЛЬ, СЕГОДНЯ)):
    print("  [%s] %s | ящик %s" % (р["event_type"], str(р["event_ts"])[:19],
                                   str(р["mailbox_id"] or "?")[:34]))

print("\n=== ГДЕ ВООБЩЕ УПОМИНАЕТСЯ BERG В ИСХОДЯЩИХ ЗА СЕГОДНЯ ===")
н = 0
for р in c.execute(
        "SELECT m.id, m.status, m.sent_at, m.mailbox_id, r.email, m.subject "
        "  FROM messages m LEFT JOIN recipients r ON r.id=m.recipient_id "
        " WHERE (m.body_rendered LIKE '%BERG%' OR m.body_rendered LIKE '%Берг%') "
        "   AND substr(COALESCE(m.sent_at, m.created_at),1,10)=? "
        " ORDER BY m.id DESC LIMIT 10", (СЕГОДНЯ,)):
    н += 1
    print("  #%-6s %-14s %s | кому %s | %s"
          % (р["id"], р["status"], str(р["sent_at"] or "—")[:16],
             str(р["email"] or "?")[:30], str(р["subject"] or "")[:40]))
if not н:
    print("  ни одного письма со словом BERG за сегодня нет")

print("\n=== ПОСЛЕДНИЕ 5 ПИСЕМ ВООБЩЕ (не залипла ли запись) ===")
for р in c.execute(
        "SELECT id, status, created_at, sent_at, subject FROM messages "
        " ORDER BY id DESC LIMIT 5"):
    print("  #%-6s %-14s создано %s отправлено %s | %s"
          % (р["id"], р["status"], str(р["created_at"])[:16],
             str(р["sent_at"] or "—")[:16], str(р["subject"] or "")[:40]))
