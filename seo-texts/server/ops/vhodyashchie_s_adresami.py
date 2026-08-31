# -*- coding: utf-8 -*-
"""Структура входящих и все, где в тексте есть посторонний адрес."""
import json
import re
import sqlite3

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=90)
c.row_factory = sqlite3.Row
r = c.execute("SELECT detail_json FROM events WHERE event_type='reply'"
              " ORDER BY id DESC LIMIT 1").fetchone()
d = json.loads(r["detail_json"] or "{}") if r else {}
print("ключи detail_json у reply: %s" % sorted(d.keys()))
for к in sorted(d.keys()):
    if к == "headers":
        continue
    print("   %-14s %s" % (к, str(d[к])[:120].replace("\n", " ")))

АДРЕС = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
НАШИ = ("kompressor-pro-expert.ru", "kompressor-air-expert.ru",
        "zernosort.ru", "prokompressor.ru")
print("\n=== ВХОДЯЩИЕ С ПОСТОРОННИМ АДРЕСОМ В ТЕКСТЕ ===")
n = 0
for r in c.execute(
        "SELECT id, event_type, recipient_id, substr(event_ts,1,19) когда,"
        "       detail_json FROM events"
        " WHERE event_type IN ('reply','reply_auto','other')"
        " ORDER BY id DESC LIMIT 400"):
    try:
        d = json.loads(r["detail_json"] or "{}") or {}
    except Exception:                                         # noqa: BLE001
        continue
    тело = ""
    for к in ("body", "text", "body_text", "plain", "content", "preview"):
        if d.get(к):
            тело = str(d[к])
            break
    if not тело:
        continue
    заг = d.get("headers") or {}
    откуда = str(заг.get("From") or "")
    q = c.execute("SELECT email, company_name FROM recipients WHERE id=?",
                  (r["recipient_id"],)).fetchone() if r["recipient_id"] else None
    прежний = str(q["email"] if q else "").lower()
    чужие = sorted({а.lower() for а in АДРЕС.findall(тело)
                    if not any(х in а.lower() for х in НАШИ)
                    and а.lower() != прежний
                    and а.lower() not in откуда.lower()})
    if not чужие:
        continue
    n += 1
    print("\n-- событие %s (%s) %s | %s"
          % (r["id"], r["event_type"], r["когда"],
             (q["company_name"] if q else "?")))
    print("   писали на %s; From: %s" % (прежний, откуда[:60]))
    print("   чужие адреса: %s" % ", ".join(чужие[:4]))
    for с in тело.strip().splitlines()[:10]:
        if с.strip():
            print("   | %s" % с.strip()[:110])
    if n >= 8:
        break
c.close()
print("\n=== ИТОГ ===")
print("входящих с посторонним адресом: %d" % n)
