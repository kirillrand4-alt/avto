# -*- coding: utf-8 -*-
"""Что лента скажет про наши восемь копий сейчас, после отправки."""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ИДЫ = (948, 2601, 3050, 3051, 3312, 3313, 3472, 3473)
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
исходные = set()
print("== ключи наших копий ==")
for r in c.execute("SELECT id, dedup_key, email, status, message_id "
                   "FROM confirm_reviews WHERE id IN " + str(ИДЫ)):
    ключ = str(r["dedup_key"] or "")
    части = ключ.split(":")
    ис = части[1] if len(части) > 2 and части[1].isdigit() else ""
    if ис:
        исходные.add(int(ис))
    mst = c.execute("SELECT status FROM messages WHERE id=?",
                    (r["message_id"],)).fetchone()
    print(f"  #{r['id']} карточка={r['status']:<9} письмо="
          f"{mst[0] if mst else '—':<9} исходный={ис or '—':<6} {ключ[:46]}")

print("\n== что отдаст лента ==")
вышло = store.kopii_avtootveta(исходные)
for ис, копии in вышло.items():
    for к in копии:
        print(f"  получатель {ис}: {к['email']:<32} "
              f"«{к['chelovecheski']}» ({к['status']})")
