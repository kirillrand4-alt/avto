# -*- coding: utf-8 -*-
"""Проверка: отбивка ушла из ленты компании, событие в журнале осталось."""
import sqlite3
import sys
sys.path.insert(0, r"C:\sender")
БАЗА = r"C:\sender\sender.db"
ИНН = "6167128827"
from sender.config import Config                                   # noqa: E402
from sender.store import Store                                     # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", БАЗА))
print("правка в загруженном коде: %s"
      % hasattr(Store, "_OTBIVKI_NE_PEREPISKA"))
print("=== лента компании (как её увидит продажник) ===")
for it in store.dialog_thread_company(ИНН):
    print("  %s %s [%s] %s :: %s"
          % (it.get("direction"), str(it.get("ts"))[:19], it.get("kind"),
             it.get("email"), str(it.get("body") or "").replace("\n", " ")[:90]))
print("=== полная техническая лента (bez_otbivok=False) ===")
try:
    for it in store.dialog_thread_company(ИНН, bez_otbivok=False):
        print("  %s %s [%s] %s" % (it.get("direction"), str(it.get("ts"))[:19],
                                   it.get("kind"), it.get("email")))
except TypeError as ex:
    print("  старый код в памяти: %s" % ex)
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
print("событие отбивки в журнале: %s"
      % c.execute("SELECT event_type FROM events WHERE id=157533").fetchone()[0])
print("карточка лида 253 [%d знаков]"
      % len(str(c.execute("SELECT need FROM leads WHERE id=253").fetchone()[0] or "")))
c.close()
