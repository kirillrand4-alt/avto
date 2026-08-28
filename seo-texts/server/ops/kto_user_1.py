# -*- coding: utf-8 -*-
import sqlite3
from collections import Counter
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
try:
    print("=== пользователи ===")
    for r in c.execute("SELECT * FROM users"):
        print("   " + " | ".join("%s=%s" % (к, str(r[к])[:40]) for к in r.keys()
                                 if к not in ("password_hash", "token_hash")))
except Exception as e:
    print("   таблицы users нет: %s" % str(e)[:60])
print("")
print("=== кто менял статусы (actor_user_id) ===")
for r in c.execute("SELECT COALESCE(actor_user_id,-1) a, COUNT(*) n FROM lead_events "
                   " WHERE action='status_changed' GROUP BY 1 ORDER BY n DESC"):
    print("   actor %-4s %4d" % (r["a"], r["n"]))
print("")
print("=== смены на not_interested по времени (сегодня) ===")
т = Counter()
for r in c.execute("SELECT substr(created_at,12,5) чм, lead_id FROM lead_events "
                   " WHERE to_status='not_interested' "
                   "   AND substr(created_at,1,10)='2026-08-28' ORDER BY created_at"):
    т[r["чм"][:4] + "0"] += 1
for к in sorted(т):
    print("   %s  %3d" % (к, т[к]))
print("")
print("=== аудит: что делал пользователь около 07:35 ===")
try:
    for r in c.execute("SELECT action, entity_type, entity_id, actor_user_id, "
                       "       created_at, detail_json FROM audit_log "
                       " WHERE created_at BETWEEN '2026-08-28T07:33' AND '2026-08-28T07:38' "
                       " ORDER BY created_at LIMIT 14"):
        print("   %s %-22s %-14s #%-6s %s" % (str(r["created_at"])[11:19], r["action"],
                                              r["entity_type"], r["entity_id"],
                                              str(r["detail_json"] or "")[:60]))
except Exception as e:
    print("   аудита нет: %s" % str(e)[:60])
c.close()
