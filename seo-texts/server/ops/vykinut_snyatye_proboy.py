# -*- coding: utf-8 -*-
"""Окончательно снять письма, которые ochered_po_probe вернул в подтверждение
(владелец 29.10: «выкинь их, чтобы я не подтвердил случайно»): последние N записей
журнала _ops/ochered-po-probe.jsonl -> карточка и письмо skipped.
    vykinut_snyatye_proboy.py <N> [--primenit]"""
import io
import json
import sqlite3
import sys
from datetime import datetime
N = int(sys.argv[1])
з = [json.loads(s) for s in io.open(r"C:\sender\_ops\ochered-po-probe.jsonl", encoding="utf-8")]
з = [x for x in з if x.get("что") == "снято"][-N:]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
т = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
n = 0
for x in з:
    print(x["id"], x["email"], x["verdict"])
    if "--primenit" in sys.argv:
        with c:
            c.execute("UPDATE messages SET status='skipped', last_error=? WHERE id=? AND status IN ('pending_review','scheduled')",
                      ("проба: %s — снято владельцем 29.10" % x["verdict"], x["id"]))
            n += c.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_at=?, updated_at=? WHERE message_id=? AND status='pending'",
                           ("проба: %s — снято владельцем 29.10" % x["verdict"], т, т, x["id"])).rowcount
print("снято карточек:", n if "--primenit" in sys.argv else "СУХОЙ ПРОГОН")
