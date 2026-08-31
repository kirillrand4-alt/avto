# -*- coding: utf-8 -*-
"""Ищу входящий, где просят писать на другой адрес."""
import json
import re
import sqlite3

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=90)
c.row_factory = sqlite3.Row
СЛОВА = re.compile(r"(?i)(пишите|напишите|направ|продублируй|дублируй|"
                   r"перешл|на адрес|на почту|на мой|отправ\w* на|"
                   r"свяжитесь|обращайтесь)")
АДРЕС = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

найдено = 0
for r in c.execute(
        "SELECT id, event_type, recipient_id, campaign_id,"
        "       substr(event_ts,1,19) когда, detail_json"
        "  FROM events WHERE event_type IN ('reply','reply_auto','other')"
        "   AND event_ts >= '2026-08-25' ORDER BY id DESC LIMIT 300"):
    try:
        d = json.loads(r["detail_json"] or "{}") or {}
    except Exception:                                         # noqa: BLE001
        continue
    тело = str(d.get("body") or d.get("text") or "")
    заг = d.get("headers") or {}
    откуда = str(заг.get("From") or "")
    тема = str(заг.get("Subject") or "")
    if not тело:
        continue
    адреса = [а for а in АДРЕС.findall(тело)
              if not а.lower().endswith(("kompressor-pro-expert.ru",
                                         "kompressor-air-expert.ru"))]
    if not (СЛОВА.search(тело) and адреса):
        continue
    свои = set()
    for а in адреса:
        свои.add(а.lower())
    # адрес получателя, которому писали
    q = c.execute("SELECT email, company_name, inn FROM recipients WHERE id=?",
                  (r["recipient_id"],)).fetchone() if r["recipient_id"] else None
    прежний = str(q["email"] if q else "").lower()
    другие = sorted(а for а in свои if а != прежний)
    if not другие:
        continue
    найдено += 1
    print("\n######## событие %s (%s) %s ########"
          % (r["id"], r["event_type"], r["когда"]))
    print("   компания: %s (ИНН %s)"
          % (q["company_name"] if q else "?", q["inn"] if q else "?"))
    print("   писали на: %s" % прежний)
    print("   From: %s" % откуда[:80])
    print("   Тема: %s" % тема[:80])
    print("   НАЙДЕННЫЕ АДРЕСА В ТЕКСТЕ: %s" % ", ".join(другие))
    print("   --- текст ---")
    for с in тело.strip().splitlines()[:18]:
        if с.strip():
            print("   | %s" % с.strip()[:110])
    if найдено >= 6:
        break
c.close()
print("\n=== ИТОГ ===")
print("подходящих входящих найдено: %d" % найдено)
