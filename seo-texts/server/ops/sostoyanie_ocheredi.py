# -*- coding: utf-8 -*-
"""Очередь подтверждений, письма прогона и версии файлов прогона."""
import os
import sqlite3
import time

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row

print("=== confirm_reviews по статусам ===")
for r in c.execute("SELECT status, COUNT(*) n FROM confirm_reviews GROUP BY status"):
    print("   %-14s %d" % (r["status"], r["n"]))

print("")
print("=== создано сегодня (25.08) ===")
for r in c.execute(
        "SELECT status, COUNT(*) n FROM confirm_reviews "
        " WHERE substr(created_at,1,10)='2026-08-25' GROUP BY status"):
    print("   %-14s %d" % (r["status"], r["n"]))

print("")
print("=== messages по статусам (сегодня) ===")
for r in c.execute(
        "SELECT status, COUNT(*) n FROM messages "
        " WHERE substr(created_at,1,10)='2026-08-25' GROUP BY status"):
    print("   %-14s %d" % (r["status"], r["n"]))

print("")
print("=== последние 5 карточек очереди ===")
for r in c.execute("SELECT id, status, created_at, substr(subject,1,50) s "
                   "FROM confirm_reviews ORDER BY id DESC LIMIT 5"):
    print("   #%-6s %-10s %s  %s" % (r["id"], r["status"],
                                     str(r["created_at"])[:19], r["s"]))
c.close()

print("")
print("=== версии файлов прогона ===")
for п in (r"C:\sender\_ops\partiya_gen.py", r"C:\sender\server\ops\partiya_gen.py",
          r"C:\sender\sender\store.py", r"C:\sender\sender\review_lenses.py"):
    if not os.path.exists(п):
        print("   %-44s НЕТ" % п)
        continue
    т = open(п, "r", encoding="utf-8", errors="replace").read()
    метки = []
    if "МОДЕЛЬ_ЛИНЗЫ" in т:
        метки.append("линза-модель")
    if "вернуть в пул" in т or "вернём в пул" in т or "в пул" in т:
        метки.append("возврат-в-пул")
    if "предыдущий ответ" in т:
        метки.append("дописка-ответа")
    if "status='pending'" in т and "skipped" in т:
        метки.append("оживление-карточки")
    if "LENS_MODEL" in т:
        метки.append("LENS_MODEL")
    print("   %-44s %6d б  %s  [%s]"
          % (п, os.path.getsize(п),
             time.strftime("%d.%m %H:%M", time.localtime(os.path.getmtime(п))),
             ", ".join(метки) or "—"))
