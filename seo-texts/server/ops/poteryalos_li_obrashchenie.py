# -*- coding: utf-8 -*-
"""Было ли событие #94446 живым письмом и попало ли оно в ленту лидов.

Письмо, ошибочно принятое за отбивку, в ленту не идёт: лид заводится по
событиям ответа, а не по dsn. Проверяем прямо: текст письма, есть ли лид
по этому получателю и какие вообще события есть от этого домена.
"""
import json
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
р = c.execute("SELECT * FROM events WHERE id=94446").fetchone()
д = json.loads(р["detail_json"] or "{}")
print("ТЕКСТ ПИСЬМА (snippet):")
print((д.get("snippet") or "(пусто)")[:1500])
print("\nтема из заголовков:", (д.get("headers") or {}).get("Subject"))
print("от кого:", (д.get("headers") or {}).get("From"))

rid = р["recipient_id"]
пол = c.execute("SELECT * FROM recipients WHERE id=?", (rid,)).fetchone()
print(f"\nполучатель #{rid}: "
      f"{(пол['company_name'] if пол else '?')} / "
      f"{(пол['email'] if пол else '?')}")

столбцы = {r[1] for r in c.execute("PRAGMA table_info(leads)").fetchall()}
if "recipient_id" in столбцы:
    лиды = c.execute("SELECT id, status, created_at FROM leads "
                     " WHERE recipient_id=?", (rid,)).fetchall()
    print(f"лидов по этому получателю: {len(лиды)}")
    for л in лиды:
        print(f"  лид #{л['id']} {л['status']} {л['created_at']}")
else:
    print("в таблице leads нет recipient_id, колонки:", sorted(столбцы)[:12])

соб = c.execute(
    "SELECT id, event_type, event_ts FROM events WHERE recipient_id=? "
    " ORDER BY id DESC LIMIT 10", (rid,)).fetchall()
print(f"\nсобытия по получателю: {len(соб)}")
for с in соб:
    print(f"  #{с['id']} {с['event_type']} {с['event_ts'][:19]}")
