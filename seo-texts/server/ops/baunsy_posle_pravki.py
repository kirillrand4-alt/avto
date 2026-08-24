# -*- coding: utf-8 -*-
"""Работает ли правка проб после перезапуска панели, и что с баунсами.

Проверяем по делам: снимает ли проба письма по «неясно» и по приговору,
уменьшилось ли число одобренных карточек, которых проба не видела, и что
происходит с баунсами за последние часы.
"""
import json
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("=== СНЯТЫЕ ПРОБОЙ ЗА СЕГОДНЯ ===")
есть = False
for р in c.execute(
        "SELECT COALESCE(decided_by,'') кем, substr(COALESCE(reason,''),1,44) п, "
        "       COUNT(*) n, MAX(decided_at) t FROM confirm_reviews "
        " WHERE status='skipped' AND COALESCE(decided_by,'') LIKE '%проба%' "
        "   AND substr(COALESCE(decided_at,''),1,10)=date('now') "
        " GROUP BY кем, п ORDER BY t DESC"):
    есть = True
    print("  %-32s %-46s %4d  последняя %s"
          % (р["кем"][:32], р["п"], р["n"], str(р["t"])[:19]))
if not есть:
    print("  решением пробы сегодня ничего не снято")

print("\n=== ПИСЬМА, СНЯТЫЕ ПРОБОЙ НАПРЯМУЮ (одобренные карточки) ===")
for р in c.execute(
        "SELECT COUNT(*) n, MAX(updated_at) t FROM messages "
        " WHERE status='skipped' AND last_error LIKE '%проба адресов%'"):
    print("  писем: %d, последнее %s" % (р["n"], str(р["t"] or "-")[:19]))
for р in c.execute(
        "SELECT substr(last_error,1,80) п, COUNT(*) n FROM messages "
        " WHERE status='skipped' AND last_error LIKE '%проба адресов%' "
        " GROUP BY п ORDER BY n DESC LIMIT 6"):
    print("    %-82s %4d" % (р["п"], р["n"]))

print("\n=== ОДОБРЕННЫЕ, КОТОРЫХ ПРОБА НЕ ВИДЕЛА (было 76) ===")
н = c.execute(
    "SELECT COUNT(*) n FROM confirm_reviews cr "
    "  JOIN recipients r ON r.id=cr.recipient_id "
    "  LEFT JOIN addr_probe p ON lower(p.email)=lower(r.email) "
    " WHERE cr.status='approved' AND p.email IS NULL").fetchone()["n"]
print("  сейчас: %d" % н)

print("\n=== ОДОБРЕННЫЕ С ПРИГОВОРОМ, У КОТОРЫХ ПИСЬМО ЕЩЁ НЕ СНЯТО ===")
строки = c.execute(
    "SELECT cr.id, r.email, p.verdict, m.status FROM confirm_reviews cr "
    "  JOIN recipients r ON r.id=cr.recipient_id "
    "  JOIN addr_probe p ON lower(p.email)=lower(r.email) "
    "  LEFT JOIN messages m ON m.id=cr.message_id "
    " WHERE cr.status IN ('approved','pending') "
    "   AND p.verdict IN ('нет ящика','нет MX','неясно') "
    "   AND COALESCE(m.status,'') NOT IN ('skipped','sent','failed')").fetchall()
print("  таких карточек: %d" % len(строки))
for р in строки[:10]:
    print("    #%-6s %-32s %-12s письмо %s"
          % (р["id"], str(р["email"])[:32], р["verdict"], р["status"]))

print("\n=== БАУНСЫ ПО ЧАСАМ ЗА СЕГОДНЯ ===")
for р in c.execute(
        "SELECT substr(event_ts,12,2) час, COUNT(*) n FROM events "
        " WHERE event_type='bounce' AND substr(event_ts,1,10)=date('now') "
        " GROUP BY час ORDER BY час"):
    print("  %s:00  %s %d" % (р["час"], "#" * р["n"], р["n"]))
о = c.execute("SELECT COUNT(*) n FROM messages WHERE status='sent' "
              "  AND substr(COALESCE(sent_at,created_at),1,10)=date('now')"
              ).fetchone()["n"]
б = c.execute("SELECT COUNT(*) n FROM events WHERE event_type='bounce' "
              "  AND substr(event_ts,1,10)=date('now')").fetchone()["n"]
print("  отправлено %d, баунсов %d → %.1f%%" % (о, б, 100.0 * б / о if о else 0))
