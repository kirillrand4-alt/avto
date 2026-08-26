# -*- coding: utf-8 -*-
"""Отклик по направлениям: КЦ против Meyer, по ящикам направления."""
import re
import sqlite3

MEYER = re.compile(r"optic-sort|zernosort|sort-systems", re.I)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row

отпр = {r["mailbox_id"]: r["n"] for r in c.execute(
    "SELECT mailbox_id, COUNT(*) n FROM messages WHERE sent_at IS NOT NULL "
    " GROUP BY mailbox_id")}
вход = {}
for r in c.execute("SELECT mailbox_id, event_type, COUNT(*) n FROM events "
                   " WHERE event_type IN ('reply','reply_auto','bounce') "
                   " GROUP BY mailbox_id, event_type"):
    вход.setdefault(r["mailbox_id"] or "", {})[r["event_type"]] = r["n"]

свод = {"kc": [0, 0, 0, 0], "meyer": [0, 0, 0, 0]}
for я, о in отпр.items():
    к = "meyer" if MEYER.search(str(я or "")) else "kc"
    в = вход.get(я, {})
    свод[к][0] += о
    свод[к][1] += в.get("reply", 0)
    свод[к][2] += в.get("reply_auto", 0)
    свод[к][3] += в.get("bounce", 0)

print("%-8s %8s %8s %8s %9s %9s %8s"
      % ("напр", "ушло", "живых", "авто", "живых %", "всего %", "отбивок"))
for к, (о, ж, а, б) in свод.items():
    print("%-8s %8d %8d %8d %8.1f%% %8.1f%% %8d"
          % (к, о, ж, а, 100.0 * ж / о if о else 0,
             100.0 * (ж + а) / о if о else 0, б))

print("")
print("=== живые ответы по дням ===")
for r in c.execute(
        "SELECT substr(event_ts,1,10) д, COUNT(*) n FROM events "
        " WHERE event_type='reply' AND event_ts >= '2026-08-15' "
        " GROUP BY д ORDER BY д"):
    print("   %s  %s" % (r["д"], "#" * r["n"] + " %d" % r["n"]))
print("")
print("=== отправлено по дням ===")
for r in c.execute(
        "SELECT substr(sent_at,1,10) д, COUNT(*) n FROM messages "
        " WHERE sent_at >= '2026-08-15' GROUP BY д ORDER BY д"):
    print("   %s  %d" % (r["д"], r["n"]))
c.close()
