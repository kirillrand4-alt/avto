# -*- coding: utf-8 -*-
"""Карточка лида #64 целиком и есть ли личный телефон у vs@koenigsauce.ru.

Человек ответил с личного адреса и попросил слать ему. В карточке при этом
стоит общий office@. Смотрим, сохранён ли настоящий адрес ответа хоть
где-то, и ищем по обогащению телефон именно этого человека.
"""
import json
import os
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
р = c.execute("SELECT * FROM leads WHERE id=64").fetchone()
print("=== лид #64 ===")
for к, з in dict(р).items():
    if з not in (None, ""):
        print(f"  {к:<18}: {str(з)[:110]}")

print("\n=== что знает событие ответа (#102453) ===")
с = c.execute("SELECT COALESCE(detail_json,'') dj FROM events WHERE id=102453").fetchone()
try:
    д = json.loads(с["dj"] or "{}")
except Exception:                                                  # noqa: BLE001
    д = {}
заг = д.get("headers") if isinstance(д.get("headers"), dict) else {}
for к in ("From", "Reply-To", "To", "Cc", "Subject", "Message-ID"):
    if заг.get(к):
        print(f"  {к:<12}: {str(заг.get(к))[:110]}")
print(f"  from_addr   : {д.get('from_addr') or '-'}")

print("\n=== обогащение по ИНН 3905029996 ===")
путь = r"C:\sender\enrich.db"
if not os.path.exists(путь):
    print("enrich.db не найден")
else:
    e = sqlite3.connect(путь)
    e.row_factory = sqlite3.Row
    таблицы = [т[0] for т in e.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    for т in таблицы:
        колонки = [к[1] for к in e.execute(f"PRAGMA table_info({т})")]
        if not any(k in колонки for k in ("inn", "INN")):
            continue
        try:
            ряды = e.execute(f"SELECT * FROM {т} WHERE inn=?",
                             ("3905029996",)).fetchall()
        except Exception:                                          # noqa: BLE001
            continue
        if not ряды:
            continue
        print(f"\n-- таблица {т}: строк {len(ряды)}")
        for ряд in ряды[:6]:
            д2 = {к: v for к, v in dict(ряд).items() if v not in (None, "")}
            интерес = {к: v for к, v in д2.items()
                       if any(s in к.lower() for s in
                              ("phone", "tel", "email", "person", "fio",
                               "name", "post", "dolzh", "role"))}
            print("   " + json.dumps(интерес or д2, ensure_ascii=False)[:300])
