# -*- coding: utf-8 -*-
"""Только чтение: виден ли лид 489 в ленте штатным методом панели."""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
путь = cfg.get("service.db_path", r"C:\sender\sender.db")
store = Store(путь)

c = sqlite3.connect("file:%s?mode=ro" % путь, uri=True, timeout=90)
c.row_factory = sqlite3.Row
print("=== reply_mailbox у лидов: заполняется ли вообще ===")
for р in c.execute("SELECT CASE WHEN IFNULL(reply_mailbox,'')='' THEN 'пусто'"
                   " ELSE 'заполнено' END k, COUNT(*) n FROM leads GROUP BY k"):
    print("  %-10s %d" % (р["k"], р["n"]))

print("\n=== СТАТУСЫ ЛИДОВ СЕЙЧАС ===")
for р in c.execute("SELECT status, COUNT(*) n FROM leads GROUP BY status"
                   " ORDER BY n DESC"):
    print("  %-16s %d" % (р["status"], р["n"]))

print("\n=== ЧТО ЕЩЁ В ОЧЕРЕДИ НА ЧИСТОЗЕРЬЕ ===")
есть = False
for р in c.execute("SELECT id, campaign_id, status, scheduled_at, subject"
                   " FROM messages WHERE recipient_id=33093"
                   " AND status IN ('scheduled','pending_review','sending')"):
    есть = True
    print("  msg=%s камп=%s %s %s | %s" % (р["id"], р["campaign_id"],
                                           р["status"], р["scheduled_at"],
                                           str(р["subject"])[:40]))
if not есть:
    print("  ничего не запланировано")
c.close()

лента = store.list_leads(limit=500)
свой = [л for л in лента if getattr(л, "id", None) == 489]
print("\n=== ШТАТНЫЙ list_leads ===")
print("  всего в выдаче: %d" % len(лента))
if свой:
    л = свой[0]
    print("  ЛИД 489 В ЛЕНТЕ: %s | %s | ИНН %s | %s | %s"
          % (л.email, str(л.company_name)[:32], л.inn, л.status, л.reply_kind))
else:
    print("  ЛИДА 489 В ВЫДАЧЕ НЕТ")
