# -*- coding: utf-8 -*-
"""Сколько дублей по одной компании уже лежит в очереди и ждёт отправки.

Правило 90 дней смотрит и на адрес, и на ИНН — send_log_history строит
условие «email ИЛИ инн». Но опирается оно на историю ОТПРАВОК
(outcome='sent'). Письмо, которое сгенерировано и стоит в очереди, но ещё
не ушло, для заслона невидимо: следующий прогон берёт второй адрес той же
компании, потому что первый формально ещё не отправлен.

Внутри одного прогона дубль ловится счётчиком «дубль строки той же
фирмы». Между прогонами — нет. В очереди сейчас сотни писем, поэтому
вопрос не теоретический: считаем, сколько компаний получат по два письма,
если очередь уйдёт как есть.
"""
import sqlite3

ЖИВЫЕ = "('scheduled','sending','pending_review')"
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("=== КОМПАНИИ С НЕСКОЛЬКИМИ ПИСЬМАМИ В ОЧЕРЕДИ ===")
строки = c.execute(
    "SELECT r.inn, COUNT(*) n, GROUP_CONCAT(DISTINCT r.email) почты, "
    "       MIN(r.company_name) имя "
    "  FROM messages m JOIN recipients r ON r.id=m.recipient_id "
    " WHERE m.status IN %s AND r.inn IS NOT NULL AND r.inn<>'' "
    " GROUP BY r.inn HAVING n > 1 ORDER BY n DESC LIMIT 20" % ЖИВЫЕ).fetchall()
for р in строки:
    print("  ИНН %-13s писем %-2s | %-30s | %s"
          % (р["inn"], р["n"], str(р["имя"] or "")[:30], str(р["почты"])[:70]))
всего = c.execute(
    "SELECT COUNT(*), SUM(n-1) FROM (SELECT COUNT(*) n FROM messages m "
    "JOIN recipients r ON r.id=m.recipient_id WHERE m.status IN %s "
    "AND r.inn IS NOT NULL AND r.inn<>'' GROUP BY r.inn HAVING n>1)"
    % ЖИВЫЕ).fetchone()
print("ИТОГО таких компаний: %s, лишних писем в них: %s"
      % (всего[0], всего[1] or 0))

print("\n=== В ОЧЕРЕДИ ЛЕЖИТ ПИСЬМО КОМПАНИИ, КОТОРОЙ УЖЕ ПИСАЛИ ===")
повтор = c.execute(
    "SELECT COUNT(DISTINCT r.inn) FROM messages m "
    "  JOIN recipients r ON r.id=m.recipient_id "
    " WHERE m.status IN %s AND r.inn IN ("
    "   SELECT r2.inn FROM messages m2 JOIN recipients r2 ON r2.id=m2.recipient_id"
    "    WHERE m2.status='sent' AND r2.inn IS NOT NULL AND r2.inn<>'')" % ЖИВЫЕ
).fetchone()[0]
print("  компаний: %d" % повтор)
for р in c.execute(
        "SELECT r.inn, r.email, m.id, m.status, m.subject, "
        "  (SELECT MAX(m2.sent_at) FROM messages m2 JOIN recipients r2 "
        "     ON r2.id=m2.recipient_id WHERE r2.inn=r.inn AND m2.status='sent')"
        "  писали_когда "
        "  FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        " WHERE m.status IN %s AND r.inn IN ("
        "   SELECT r2.inn FROM messages m2 JOIN recipients r2 "
        "     ON r2.id=m2.recipient_id WHERE m2.status='sent' "
        "    AND r2.inn IS NOT NULL AND r2.inn<>'') "
        " ORDER BY писали_когда DESC LIMIT 15" % ЖИВЫЕ):
    print("  ИНН %-13s %-30s | письмо #%-6s %-14s | уже писали %s"
          % (р["inn"], str(р["email"] or "")[:30], р["id"], р["status"],
             str(р["писали_когда"])[:16]))

print("\n=== КОГДА УХОДИЛИ ИЗВЕСТНЫЕ ПОВТОРЫ ===")
for инн in ("7713468789", "2124009521", "7816693698", "5320000979",
            "5262382451", "5406582905"):
    ряд = c.execute(
        "SELECT m.sent_at, r.email FROM messages m "
        "  JOIN recipients r ON r.id=m.recipient_id "
        " WHERE r.inn=? AND m.status='sent' ORDER BY m.sent_at", (инн,)).fetchall()
    if len(ряд) > 1:
        print("  ИНН %s:" % инн)
        for р in ряд:
            print("      %s  %s" % (str(р["sent_at"])[:16],
                                    str(р["email"] or "")[:40]))

print("\n=== РАЗНООБРАЗИЕ ТЕМ ЗА СЕГОДНЯ ===")
всего_т, разных = c.execute(
    "SELECT COUNT(*), COUNT(DISTINCT subject) FROM messages "
    "WHERE status='sent' AND substr(sent_at,1,10)=date('now')").fetchone()
print("  писем %s, разных тем %s" % (всего_т, разных))
for р in c.execute(
        "SELECT subject, COUNT(*) n FROM messages WHERE status='sent' "
        "AND substr(sent_at,1,10)=date('now') GROUP BY subject "
        "HAVING n>1 ORDER BY n DESC LIMIT 10"):
    print("  %-3s | %s" % (р["n"], str(р["subject"])[:80]))
