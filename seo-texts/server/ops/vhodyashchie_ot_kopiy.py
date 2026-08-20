# -*- coding: utf-8 -*-
"""Входящие письма с этих адресов: там подпись, а в подписи имя.

Владелец: «имена есть в письмах которые нам написали / емейлы же берутся
из писем для копий». Значит источник имени — само входящее.
"""
import sqlite3
import sys

АДРЕСА = [a.lower() for a in sys.argv[1:] if "@" in a]
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("== таблицы, где может лежать входящее ==")
for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    n = c.execute(f"SELECT COUNT(*) FROM [{r[0]}]").fetchone()[0]
    if n and any(k in r[0] for k in ("event", "lead", "mail", "msg", "reply",
                                     "confirm", "message")):
        print(f"  {r[0]:<22} {n}  {[x[1] for x in c.execute(f'PRAGMA table_info([{r[0]}])')]}")

print("\n== ищем адрес ВНУТРИ входящего (там From и подпись) ==")
for а in АДРЕСА:
    нашли = False
    for r in c.execute(
            "SELECT event_type, event_ts, detail_json FROM events "
            "WHERE lower(COALESCE(detail_json,'')) LIKE ? "
            "ORDER BY id DESC LIMIT 2", (f"%{а}%",)):
        нашли = True
        print(f"  {а}: [{r['event_type']}] {str(r['event_ts'])[:16]}")
        print(f"     {str(r['detail_json'])[:700]}")
    for r in c.execute(
            "SELECT id, status, COALESCE(need,'') need, company_name "
            "FROM leads WHERE lower(COALESCE(email,''))=? "
            "OR lower(COALESCE(need,'')) LIKE ?", (а, f"%{а}%")):
        нашли = True
        print(f"  {а}: лид #{r['id']} {r['company_name']} — "
              f"{str(r['need'])[:300]}")
    if not нашли:
        print(f"  {а}: входящего не нашлось")
