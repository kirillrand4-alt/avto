# -*- coding: utf-8 -*-
"""Только чтение: переписка по лиду 490 (КриоГаз Северо-Запад)."""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
путь = cfg.get("service.db_path", r"C:\sender\sender.db")
store = Store(путь)

c = sqlite3.connect("file:%s?mode=ro" % путь, uri=True)
c.row_factory = sqlite3.Row
л = c.execute("SELECT * FROM leads WHERE id=490").fetchone()
print("=== ЛИД 490 ===")
print("  %s | %s | ИНН %s | получатель %s | статус %s | метка %s"
      % (л["email"], л["company_name"], л["inn"], л["recipient_id"],
         л["status"], л["reply_kind"]))
c.close()

for имя, вызов in (("ПО ПОЛУЧАТЕЛЮ 30163", lambda: store.dialog_thread(30163)),
                   ("ПО КОМПАНИИ ИНН 5003063216",
                    lambda: store.dialog_thread_company("5003063216"))):
    print("\n=== ПЕРЕПИСКА %s ===" % имя)
    for it in вызов():
        тело = " ".join(str(it.get("body") or "").split())
        print("  [%s] %s  ящик=%s"
              % (it.get("direction"), str(it.get("ts"))[:19],
                 it.get("mailbox_id")))
        print("      тема: %s" % str(it.get("subject"))[:60])
        print("      %s" % (тело[:180] if тело else "ТЕЛО ПУСТОЕ"))
