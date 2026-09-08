# -*- coding: utf-8 -*-
"""Только чтение: 1) на какой адрес уйдёт ответ из карточки 2) потерянные ответы."""
import io
import json
import re
import sqlite3

т = io.open(r"C:\sender\sender\api\app.py", encoding="utf-8",
            errors="ignore").read()
i = т.find('@app.post("/leads/{lead_id}/reply")')
j = т.find("ВЛОЖЕНИЯ_КОРЕНЬ", i)
print("=== ХВОСТ МАРШРУТА /leads/{id}/reply ===")
print(т[j:j + 2000])

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
МАШИНА = ("noreply", "no-reply", "no_reply", "donotreply", "do-not-reply",
          "daemon", "postmaster@", "notification", "notifications@", "notify@",
          "robot@", "bounce@", "abuse@", "mailer-daemon", "support@yandex",
          "info@yandex")
писали = {r[0] for r in c.execute(
    "SELECT DISTINCT recipient_id FROM messages WHERE sent_at IS NOT NULL")}
адреса = {}
for r in c.execute("SELECT id, email FROM recipients"):
    адреса.setdefault((r["email"] or "").lower(), r["id"])
домены = {}
for r in c.execute("SELECT id, domain FROM recipients WHERE domain IS NOT NULL"):
    домены.setdefault((r["domain"] or "").lower(), r["id"])

потеряшки = []
for r in c.execute("SELECT id, event_ts, recipient_id, mailbox_id, detail_json"
                   " FROM events WHERE event_type='other' ORDER BY id"):
    if r["recipient_id"]:
        continue
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:                                            # noqa: BLE001
        continue
    h = d.get("headers") or {}
    от = str(h.get("From") or "")
    низ = от.lower()
    текст = " ".join(str(d.get("snippet") or "").split())
    if any(м in низ for м in МАШИНА):
        continue
    if not re.search(r"[а-яА-Я]{8}", текст):
        continue
    адрес = ""
    м = re.search(r"[\w.+-]+@[\w.-]+", низ)
    if м:
        адрес = м.group(0)
    домен = адрес.split("@")[-1] if адрес else ""
    подсказка = ""
    if адрес in адреса:
        подсказка = "адрес есть в базе, получатель %d" % адреса[адрес]
    elif домен in домены:
        подсказка = "домен есть в базе, получатель %d" % домены[домен]
    потеряшки.append((r["id"], str(r["event_ts"])[:16], от[:42],
                      str(h.get("Subject") or "")[:26], текст[:70], подсказка))

print("\n" + "=" * 78)
print("=== ЖИВЫЕ ПИСЬМА БЕЗ ПРИВЯЗКИ: %d ===" % len(потеряшки))
for eid, ts, от, тема, текст, подсказка in потеряшки:
    print("\n  ev=%-7s %s  %s" % (eid, ts, от))
    print("      тема: %-26s %s" % (тема, подсказка))
    print("      %s" % текст)
