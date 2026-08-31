# -*- coding: utf-8 -*-
"""Куда делся ответ, написанный из ленты лидов."""
import json
import sqlite3
import time

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
c.row_factory = sqlite3.Row
print("сейчас на сервере: %s (UTC %s)"
      % (time.strftime("%d.%m %H:%M:%S"),
         time.strftime("%H:%M:%S", time.gmtime())))

print("\n=== ПОСЛЕДНИЕ 12 КАРТОЧЕК confirm_reviews ===")
for r in c.execute(
        "SELECT id, campaign_id, COALESCE(kind,'outbound') kind, status,"
        "       email, substr(created_at,1,19) создана,"
        "       substr(COALESCE(subject,''),1,42) тема, message_id,"
        "       COALESCE(in_reply_to,'') irt, COALESCE(thread_id,'') tid,"
        "       COALESCE(manual_email_ts,'') mts"
        "  FROM confirm_reviews ORDER BY id DESC LIMIT 12"):
    print("   %6s к%-3s %-9s %-10s %-26s %s"
          % (r["id"], r["campaign_id"], r["kind"], r["status"],
             (r["email"] or "")[:26], r["создана"]))
    if r["kind"] != "outbound":
        print("          тема: %s | msg=%s irt=%s thread=%s manual=%s"
              % (r["тема"], r["message_id"], (r["irt"] or "")[:20],
                 (r["tid"] or "")[:20], r["mts"]))

print("\n=== ОТВЕТЫ (kind=reply) ЗА СУТКИ ===")
n = 0
for r in c.execute(
        "SELECT id, status, email, substr(created_at,1,19) создана, reason"
        "  FROM confirm_reviews WHERE COALESCE(kind,'')='reply'"
        "   AND created_at >= datetime('now','-1 day') ORDER BY id DESC LIMIT 10"):
    n += 1
    print("   %6s %-10s %-28s %s  %s"
          % (r["id"], r["status"], (r["email"] or "")[:28], r["создана"],
             str(r["reason"] or "")[:40]))
print("   всего за сутки: %d" % n)

print("\n=== ЧЕРНОВИКИ ОТВЕТОВ В lead-таблицах ===")
таблицы = [r[0] for r in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%lead%'")]
print("   таблицы: %s" % ", ".join(таблицы))
for т in таблицы:
    столбцы = [x[1] for x in c.execute("PRAGMA table_info(%s)" % т)]
    if "created_at" in столбцы:
        n = c.execute("SELECT COUNT(*) FROM %s WHERE created_at >="
                      " datetime('now','-2 hours')" % т).fetchone()[0]
        print("   %-14s строк за 2 часа: %d  (колонки: %s)"
              % (т, n, ", ".join(столбцы[:10])))

print("\n=== ПОСЛЕДНИЕ СОБЫТИЯ ===")
for r in c.execute("SELECT id, event_type, recipient_id, campaign_id,"
                   "       substr(event_ts,1,19) когда"
                   "  FROM events ORDER BY id DESC LIMIT 8"):
    print("   %6s %-14s rid=%-6s к%-3s %s" % tuple(r))

print("\n=== АУДИТ ЗА ПОСЛЕДНИЙ ЧАС ===")
try:
    for r in c.execute("SELECT id, action, actor_user_id, entity_type,"
                       "       entity_id, substr(created_at,1,19) когда"
                       "  FROM audit_log WHERE created_at >="
                       "   datetime('now','-1 hour') ORDER BY id DESC LIMIT 12"):
        print("   %6s %-24s user=%-4s %s/%s %s" % tuple(r))
except sqlite3.OperationalError as e:
    print("   %s" % e)
c.close()
