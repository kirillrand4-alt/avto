# -*- coding: utf-8 -*-
"""Компактно: состояние карточек лидов после дописывания вторых ответов."""
import sqlite3

conn = sqlite3.connect(r"C:\sender\sender.db")
conn.row_factory = sqlite3.Row
for cid in (28, 43, 61, 63):
    r = conn.execute("SELECT * FROM leads WHERE id=?", (cid,)).fetchone()
    if r is None:
        print("#%d — нет" % cid)
        continue
    d = dict(r)
    need = d.get("need") or ""
    печ = need.count("--- предыдущий ответ ---")
    print("#%-4s вид=%-14s тел=%-16s статус=%-10s ответов=%d длина=%d обновлена=%s"
          % (d.get("id"), d.get("reply_kind"), d.get("phone") or "—",
             d.get("status"), печ + 1, len(need), str(d.get("updated_at"))[:19]))
conn.close()
