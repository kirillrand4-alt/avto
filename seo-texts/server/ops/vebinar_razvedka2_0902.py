# -*- coding: utf-8 -*-
"""Только чтение. Прецедент «Вебинар 28.08»: как заводили, что слали.
Плюс полная схема recipients и messages. Важное печатаем в конце."""
import inspect
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

print("=== ПРЕЦЕДЕНТ: группа «Вебинар 28.08» ===")
ид = []
for р in c.execute("SELECT id, extra_json FROM recipients"
                   " WHERE extra_json LIKE '%Вебинар 28.08%'"):
    ид.append(р["id"])
print("  получателей: %d" % len(ид))
if ид:
    об = c.execute("SELECT * FROM recipients WHERE id=?", (ид[0],)).fetchone()
    print("  пример extra_json: %s" % str(об["extra_json"])[:300])
    print("  source=%s division=%s" % (об["source"] if "source" in об.keys() else "?",
                                       об["division"] if "division" in об.keys() else "?"))
    впис = ",".join("?" * len(ид))
    for р in c.execute(
            "SELECT campaign_id, status, COUNT(*) n FROM messages"
            " WHERE recipient_id IN (%s) GROUP BY campaign_id, status" % впис, ид):
        print("  письма: кампания=%s статус=%s n=%d"
              % (р["campaign_id"], р["status"], р["n"]))
    м = c.execute("SELECT * FROM messages WHERE recipient_id IN (%s)"
                  " ORDER BY id DESC LIMIT 1" % впис, ид).fetchone()
    if м:
        print("  тема последнего: %s" % str(м["subject"])[:80])

print("\n=== МЕТОДЫ Store: завести кампанию / получателя / письмо ===")
try:
    from sender.config import Config
    from sender.store import Store
    cfg = Config.load(r"C:\sender\sender.yaml")
    store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
    for имя in sorted(dir(store)):
        if имя.startswith("_"):
            continue
        if any(k in имя.lower() for k in ("campaign", "recipient", "message",
                                          "suppress", "enqueue", "queue")):
            f = getattr(store, имя)
            if callable(f):
                print("  %-30s %s" % (имя, str(inspect.signature(f))[:120]))
except Exception as ex:
    print("  ошибка: %s" % str(ex)[:200])

print("\n=== messages: колонки ===")
мк = [r["name"] for r in c.execute("PRAGMA table_info(messages)")]
print("  " + ", ".join(мк))

print("\n=== recipients: ПОЛНАЯ СХЕМА ===")
рк = [r["name"] for r in c.execute("PRAGMA table_info(recipients)")]
for r in c.execute("PRAGMA table_info(recipients)"):
    print("  %-18s %-10s notnull=%s dflt=%s" % (r["name"], r["type"],
                                                r["notnull"], str(r["dflt_value"])[:20]))
print("  ИТОГО колонок: %d" % len(рк))
