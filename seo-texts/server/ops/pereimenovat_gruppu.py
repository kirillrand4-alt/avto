# -*- coding: utf-8 -*-
"""Переименовать группу: имя с пробелом не доезжает до partiya_gen (аргумент
gruppa=... разбивается по пробелу и «182» уходит позиционным)."""
import json
import sqlite3
import sys
import time

СТАРО = "Спасённые 182"
НОВО = "spaseno182"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
n = 0
for rid, ex in c.execute("SELECT id, extra_json FROM recipients "
                         " WHERE COALESCE(extra_json,'') LIKE ?",
                         ("%" + СТАРО + "%",)).fetchall():
    try:
        d = json.loads(ex or "{}") or {}
    except Exception:                                            # noqa: BLE001
        continue
    гр = list(d.get("gruppy") or [])
    if СТАРО not in гр:
        continue
    гр = [НОВО if g == СТАРО else g for g in гр]
    d["gruppy"] = гр
    c.execute("UPDATE recipients SET extra_json=?, updated_at=? WHERE id=?",
              (json.dumps(d, ensure_ascii=False),
               time.strftime("%Y-%m-%dT%H:%M:%S"), rid))
    n += 1
c.commit()
c.close()
print("переименовано получателей: %d -> группа %r" % (n, НОВО))
