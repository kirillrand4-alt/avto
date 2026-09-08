# -*- coding: utf-8 -*-
"""Только чтение: как ответы попадают в ленту и что известно про Чистозерье."""
import io
import os
import re
import sqlite3

print("=== ФАЙЛЫ, ГДЕ ЖИВЁТ ЛОГИКА ОТВЕТОВ/ЛЕНТЫ ===")
for корень in (r"C:\sender\sender", r"C:\sender\server"):
    for путь, пп, фф in os.walk(корень):
        пп[:] = [п for п in пп if п not in ("__pycache__", ".git", "node_modules")]
        for ф in фф:
            if not ф.endswith((".py", ".html", ".js")):
                continue
            п = os.path.join(путь, ф)
            try:
                т = io.open(п, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            метки = []
            if "лента" in т.lower() or "lenta" in т.lower():
                метки.append("лента")
            if "imap" in т.lower():
                метки.append("imap")
            if "'reply'" in т or '"reply"' in т:
                метки.append("reply")
            if метки:
                print("  %-58s %s" % (п.replace(r"C:\sender", "")[:58],
                                      ",".join(метки)))

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

print("\n=== СХЕМА events ===")
for р in c.execute("PRAGMA table_info(events)"):
    print("  %-18s %s" % (р["name"], р["type"]))

print("\n=== ТИПЫ СОБЫТИЙ ЗА 7 ДНЕЙ ===")
for р in c.execute("SELECT event_type, count(*) n FROM events"
                   " WHERE created_at >= date('now','-7 day')"
                   " GROUP BY event_type ORDER BY n DESC"):
    print("  %-16s %d" % (р["event_type"], р["n"]))

print("\n=== ПОИСК ЧИСТОЗЕРЬЯ ===")
кто = list(c.execute(
    "SELECT r.id, r.email, r.inn, r.company FROM recipients r"
    " WHERE r.email LIKE '%chistozer%' OR r.company LIKE '%истозерь%'"
    " OR r.email LIKE '%gnezdalova%'"))
for р in кто:
    print("  recipient id=%s %s inn=%s %s"
          % (р["id"], р["email"], р["inn"], str(р["company"])[:40]))
if not кто:
    print("  в recipients не найдено")

for р in кто:
    for m in c.execute(
            "SELECT id, campaign_id, status, sent_at, mailbox_id, subject"
            " FROM messages WHERE recipient_id=? ORDER BY id", (р["id"],)):
        print("    письмо id=%s камп=%s %s %s ящик=%s | %s"
              % (m["id"], m["campaign_id"], m["status"], m["sent_at"],
                 m["mailbox_id"], str(m["subject"])[:45]))
    for e in c.execute(
            "SELECT id, event_type, created_at FROM events WHERE recipient_id=?"
            " ORDER BY id", (р["id"],)):
        print("    событие %s %s %s" % (e["id"], e["event_type"], e["created_at"]))
