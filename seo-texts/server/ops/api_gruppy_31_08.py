# -*- coding: utf-8 -*-
"""Только чтение: как панель хранит группы и как снимать карточку очереди."""
import inspect
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config    # noqa: E402
from sender.store import Store      # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

print("=== МЕТОДЫ Store про группы / очередь ===")
for имя in dir(store):
    if имя.startswith("__"):
        continue
    if any(k in имя.lower() for k in ("group", "gruppa", "confirm", "extra", "recipient")):
        try:
            f = getattr(store, имя)
            if callable(f):
                print("  %-28s %s" % (имя, str(inspect.signature(f))[:110]))
        except Exception:
            print("  %-28s (не функция)" % имя)

print("\n=== recipient_groups(): форма ===")
try:
    г = store.recipient_groups()
    print("  ключи:", list(г.keys()))
    по_id = г.get("по_id") or {}
    print("  записей по_id: %d" % len(по_id))
    прим = list(по_id.items())[:3]
    for rid, gr in прим:
        print("    %s -> %s" % (rid, gr))
    имена = {}
    for gr in по_id.values():
        for x in (gr or []):
            имена[x] = имена.get(x, 0) + 1
    print("  все группы:", sorted(имена.items(), key=lambda x: -x[1])[:12])
except Exception as ex:
    print("  ошибка:", str(ex)[:120])

print("\n=== где лежит группа физически ===")
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
р = c.execute("SELECT id, extra_json FROM recipients"
              " WHERE extra_json LIKE '%gruppy%' LIMIT 1").fetchone()
if р:
    d = json.loads(р["extra_json"])
    print("  recipients.extra_json ключи:", sorted(d.keys()))
    print("  gruppy:", d.get("gruppy"))

print("\n=== ИТОГ ===")
print("  сигнатуры выше показывают, чем менять статус карточки и группы")
