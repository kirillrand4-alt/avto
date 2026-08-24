# -*- coding: utf-8 -*-
"""Только карточка лида #64 и заголовки ответа - без обогащения.

Прошлый вывод обрезался по объёму и съел именно эту часть, а она и нужна:
хранит ли карточка адрес, С КОТОРОГО ответили, или только общий.
"""
import json
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
р = c.execute("SELECT * FROM leads WHERE id=64").fetchone()
print("=== лид #64 ===")
for к, з in dict(р).items():
    print(f"  {к:<18}: {'' if з is None else str(з)[:90]}")
с = c.execute("SELECT COALESCE(detail_json,'') dj FROM events WHERE id=102453").fetchone()
д = json.loads(с["dj"] or "{}")
заг = д.get("headers") if isinstance(д.get("headers"), dict) else {}
print("\n=== заголовки ответа ===")
for к in ("From", "Reply-To", "To", "Message-ID", "In-Reply-To"):
    print(f"  {к:<12}: {str(заг.get(к) or '-')[:90]}")
print(f"  from_addr   : {д.get('from_addr') or '-'}")
