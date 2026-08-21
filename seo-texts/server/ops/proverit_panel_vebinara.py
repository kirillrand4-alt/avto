# -*- coding: utf-8 -*-
"""Проверить, что в снимках панели вебинара есть данные, а не пустышки."""
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
with store._lock:
    строки = store._conn.execute(
        "SELECT id, inn, COALESCE(panel_json,'') FROM confirm_reviews "
        " WHERE dedup_key LIKE 'vebinar28:%' ORDER BY id LIMIT 6").fetchall()

пустых = 0
for кид, инн, j in строки:
    if not j:
        print(f"№{кид}: снимка НЕТ")
        пустых += 1
        continue
    п = json.loads(j)
    оц = п.get("scoring") or {}
    комп = п.get("company") or {}
    конт = п.get("contact") or {}
    балл = оц.get("total") or оц.get("score")
    print(f"№{кид} ИНН {инн}: балл={балл} "
          f"компания={(комп.get('name') or '—')[:28]!r} "
          f"выручка={комп.get('revenue_h') or комп.get('revenue') or '—'} "
          f"контакт={(конт.get('person') or '—')[:24]!r} "
          f"роль={конт.get('role') or '—'}")
    if балл in (None, 0) and not комп.get("name"):
        пустых += 1
print(f"\nпустых снимков среди показанных: {пустых}")
