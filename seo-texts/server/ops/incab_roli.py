# -*- coding: utf-8 -*-
"""Почему для Инкаба выбран отдел продаж, а не снабжение."""
import io
import json
import sqlite3

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
s.row_factory = sqlite3.Row
инн = None
print("=== получатели на incab.ru ===")
for r in s.execute("SELECT id, email, inn, company_name, source, created_at "
                   "  FROM recipients WHERE email LIKE '%@incab.ru' "
                   "     OR email LIKE '%@incab.co'"):
    инн = инн or str(r["inn"] or "")
    print("   rid %-6s %-28s ИНН %-13s источник %-22s %s"
          % (r["id"], r["email"], r["inn"], str(r["source"])[:22],
             str(r["created_at"])[:16]))
print("")
print("=== письма ===")
for r in s.execute(
        "SELECT m.id, m.status, m.sent_at, rc.email FROM messages m "
        "  JOIN recipients rc ON rc.id=m.recipient_id "
        " WHERE rc.inn=? ORDER BY m.sent_at", (инн,)):
    print("   msg %-6s %-9s %s  %s" % (r["id"], r["status"],
                                       str(r["sent_at"])[:16], r["email"]))
уже = {(r[0] or "").lower() for r in s.execute(
    "SELECT email FROM recipients WHERE email IS NOT NULL")}
стоп = {(r[0] or "").lower() for r in s.execute(
    "SELECT value FROM suppression WHERE scope IN ('email','address')")}
s.close()

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=60)
e.row_factory = sqlite3.Row
print("")
print("=== что знает обогащение про эту компанию ===")
for r in e.execute("SELECT email, role, person, probe_verdict, mx_ok, source "
                   "  FROM emails WHERE inn=? ORDER BY role", (инн,)):
    п = (r["email"] or "").lower()
    метки = []
    if п in уже:
        метки.append("уже получатель")
    if п in стоп:
        метки.append("СТОП-ЛИСТ")
    print("   %-30s роль %-20s проба %-14s %s"
          % (п[:30], str(r["role"] or "—")[:20], str(r["probe_verdict"] or "—")[:14],
             ", ".join(метки)))
e.close()

print("")
print("=== в какой партии этот адрес ===")
for ф, п in ((r"C:\sender\_ops\vtorye-adresa.jsonl", 1),
             (r"C:\sender\_ops\vtorye-adresa-2.jsonl", 2)):
    try:
        for с in io.open(ф, encoding="utf-8"):
            d = json.loads(с)
            if "incab" in str(d.get("email", "")):
                print("   партия %d: %s (карточка %s)" % (п, d["email"], d["review"]))
    except FileNotFoundError:
        pass
