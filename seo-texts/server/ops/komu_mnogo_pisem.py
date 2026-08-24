# -*- coding: utf-8 -*-
"""Кому ушло по многу писем и почему заслоны это пропустили.

Владелец 24.08 показал ящик: тред «Вопрос по контролю включений в готовой
продукции» на семь писем, и два наших ушли сегодня с разницей в четыре
минуты — 15:33 и 15:37, — при том что человек ответил ещё в 12:34.

Так быть не должно: правило 90 дней (confirm._recent_contact) обязано
снимать повторный контакт, а ответ клиента — останавливать цепочку. Ищем
факт: кто получил больше одного письма, с каких ящиков, по каким
кампаниям, и совпадает ли у них ИНН.
"""
import sqlite3
import time

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
СЕГОДНЯ = time.strftime("%Y-%m-%d")

print("=== ПОЛУЧАТЕЛИ С БОЛЕЕ ЧЕМ ОДНИМ ОТПРАВЛЕННЫМ ПИСЬМОМ ===")
строки = c.execute(
    "SELECT m.recipient_id, COUNT(*) n, MIN(m.sent_at) первое, "
    "       MAX(m.sent_at) последнее, r.email, r.inn, r.company_name "
    "  FROM messages m LEFT JOIN recipients r ON r.id=m.recipient_id "
    " WHERE m.status='sent' AND m.sent_at IS NOT NULL "
    " GROUP BY m.recipient_id HAVING n > 1 "
    " ORDER BY n DESC, последнее DESC LIMIT 25").fetchall()
print("таких получателей (первые 25 по числу писем):")
for р in строки:
    print("  %-5s писем %-3s %s .. %s | %s | ИНН %s | %s"
          % (р["recipient_id"], р["n"], str(р["первое"])[:16],
             str(р["последнее"])[:16], str(р["email"] or "?")[:34],
             р["inn"], str(р["company_name"] or "")[:28]))

всего = c.execute(
    "SELECT COUNT(*) FROM (SELECT recipient_id FROM messages "
    "WHERE status='sent' GROUP BY recipient_id HAVING COUNT(*)>1)").fetchone()[0]
print("ИТОГО получателей с повтором: %d" % всего)

print("\n=== ПОВТОРЫ ЗА СЕГОДНЯ ===")
for р in c.execute(
        "SELECT m.recipient_id, COUNT(*) n, r.email, r.inn "
        "  FROM messages m LEFT JOIN recipients r ON r.id=m.recipient_id "
        " WHERE m.status='sent' AND substr(m.sent_at,1,10)=? "
        " GROUP BY m.recipient_id HAVING n > 1 ORDER BY n DESC LIMIT 15",
        (СЕГОДНЯ,)):
    print("  #%-5s %d писем | %s | ИНН %s"
          % (р["recipient_id"], р["n"], str(р["email"] or "?")[:38], р["inn"]))

print("\n=== ТРЕД ПРО ВКЛЮЧЕНИЯ В ГОТОВОЙ ПРОДУКЦИИ ===")
for р in c.execute(
        "SELECT id, recipient_id, mailbox_id, status, sent_at, thread_id, "
        "       subject, campaign_id FROM messages "
        " WHERE subject LIKE '%включен%' OR subject LIKE '%готовой продукц%' "
        " ORDER BY id DESC LIMIT 15"):
    print("  #%-6s пол.%-6s %-34s %-10s %s | %s"
          % (р["id"], р["recipient_id"], str(р["mailbox_id"] or "?")[:34],
             р["status"], str(р["sent_at"])[:16], str(р["subject"])[:46]))

print("\n=== ОДИН И ТОТ ЖЕ ИНН РАЗНЫМИ СТРОКАМИ ПОЛУЧАТЕЛЕЙ ===")
for р in c.execute(
        "SELECT r.inn, COUNT(DISTINCT r.id) строк, COUNT(m.id) писем, "
        "       GROUP_CONCAT(DISTINCT r.email) почты "
        "  FROM recipients r JOIN messages m ON m.recipient_id=r.id "
        " WHERE m.status='sent' AND r.inn IS NOT NULL AND r.inn<>'' "
        " GROUP BY r.inn HAVING строк > 1 ORDER BY писем DESC LIMIT 12"):
    print("  ИНН %-14s строк %-3s писем %-3s | %s"
          % (р["inn"], р["строк"], р["писем"], str(р["почты"])[:90]))

print("\n=== ПИСАЛИ ЛИ ТЕМ, КТО УЖЕ ОТВЕТИЛ ===")
for р in c.execute(
        "SELECT e.recipient_id, MIN(e.event_ts) ответил, "
        "  (SELECT COUNT(*) FROM messages m WHERE m.recipient_id=e.recipient_id "
        "     AND m.status='sent' AND m.sent_at > MIN(e.event_ts)) после, "
        "  (SELECT r.email FROM recipients r WHERE r.id=e.recipient_id) почта "
        "  FROM events e WHERE e.event_type='reply' "
        " GROUP BY e.recipient_id HAVING после > 0 "
        " ORDER BY после DESC LIMIT 15"):
    print("  пол.%-6s ответил %s, потом получил ещё %s | %s"
          % (р["recipient_id"], str(р["ответил"])[:16], р["после"],
             str(р["почта"] or "?")[:36]))
