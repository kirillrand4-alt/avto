# -*- coding: utf-8 -*-
"""Карточки лидов, созданные/обновлённые сегодня."""
import sqlite3

conn = sqlite3.connect(r"C:\sender\sender.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT id, recipient_id, reply_kind, phone, status, dedup_key, "
    "length(need) AS n, created_at, updated_at FROM leads "
    "WHERE created_at >= '2026-08-25' OR updated_at >= '2026-08-25' "
    "ORDER BY id").fetchall()
print("свежих карточек: %d" % len(rows))
for r in rows:
    print("#%-4s пол=%-6s вид=%-12s тел=%-16s len=%-5s созд=%s обн=%s  ключ=%s"
          % (r["id"], r["recipient_id"], r["reply_kind"], r["phone"] or "—",
             r["n"], str(r["created_at"])[:19], str(r["updated_at"])[:19],
             str(r["dedup_key"])[:40]))
print("")
for cid in (28, 43):
    r = conn.execute("SELECT id, recipient_id, dedup_key FROM leads WHERE id=?",
                     (cid,)).fetchone()
    print("#%s пол=%s ключ=%s" % (r["id"], r["recipient_id"], r["dedup_key"]))
conn.close()
