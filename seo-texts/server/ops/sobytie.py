# -*- coding: utf-8 -*-
"""Показать событие: sobytie.py <event_id> — тип, ящик, адрес, текст ошибки, сколько таких у ящика."""
import json
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
е = dict(c.execute("SELECT * FROM events WHERE id=?", (int(sys.argv[1]),)).fetchone())
д = json.loads(е.pop("detail_json") or "{}")
print(е)
print(json.dumps(д, ensure_ascii=False)[:900])
мб = е.get("mailbox_id")
print("у ящика за сегодня:", [tuple(x) for x in c.execute("SELECT event_type, count(*) FROM events WHERE mailbox_id=? AND event_ts>=date('now') GROUP BY 1", (мб,)).fetchall()])
print("спам-отказы по ящикам за 2 дня:", sorted([tuple(x) for x in c.execute("SELECT mailbox_id, count(*) FROM events WHERE event_ts>=date('now','-1 day') AND detail_json LIKE '%SPAM%' GROUP BY 1").fetchall()], key=lambda x: -x[1]))
print("=== СОБЫТИЕ ===")
