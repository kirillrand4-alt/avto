# -*- coding: utf-8 -*-
"""Только чтение: поля элементов переписки и откуда берётся thread_id."""
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
print("=== есть ли thread_id в таблицах ===")
for т in ("messages", "events", "leads"):
    поля = [р["name"] for р in c.execute("PRAGMA table_info(%s)" % т)]
    print("  %-10s thread_id=%s rfc=%s"
          % (т, "thread_id" in поля,
             [п for п in поля if "rfc" in п or "msgid" in п]))

print("\n=== пример: как выглядят ветки у компании с нормальной склейкой ===")
for р in c.execute("SELECT inn FROM leads WHERE IFNULL(thread_id,'')<>''"
                   " AND inn IS NOT NULL LIMIT 1"):
    for it in store.dialog_thread_company(р["inn"]):
        print("  [%s] thread_id=%r rfc=%r in_reply_to=%r"
              % (it.get("direction"), it.get("thread_id"),
                 str(it.get("rfc_message_id"))[:34],
                 str(it.get("in_reply_to"))[:34]))
c.close()

print("\n=== ЧИСТОЗЕРЬЕ: чем элементы НЕ склеились ===")
for it in store.dialog_thread(33093):
    print("  [%s] %s" % (it.get("direction"), str(it.get("subject"))[:40]))
    print("       адрес=%s" % it.get("email"))
    print("       thread_id=%r" % it.get("thread_id"))
    print("       rfc_message_id=%r" % str(it.get("rfc_message_id"))[:50])
    print("       in_reply_to=%r references=%r"
          % (it.get("in_reply_to"), str(it.get("references"))[:40]))
    print("       ключи: %s" % sorted(it.keys()))
