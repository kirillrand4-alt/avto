# -*- coding: utf-8 -*-
"""Только чтение: что панель показывает в карточке лида 489 (переписка)."""
import inspect
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

имена = [и for и, _ in inspect.getmembers(Store, inspect.isfunction)
         if "dialog" in и.lower() or "perepisk" in и.lower()
         or "karto" in и.lower()]
print("=== МЕТОДЫ ПРО ПЕРЕПИСКУ ===")
for и in имена:
    print("  %s%s" % (и, str(inspect.signature(getattr(Store, и)))[:120]))

for и in имена:
    ф = getattr(store, и)
    for попытка in ({"recipient_id": 33093}, {"inn": "5405089983"},
                    {"lead_id": 489}):
        try:
            рез = ф(**попытка)
        except Exception as ex:                                   # noqa: BLE001
            continue
        print("\n=== %s(%s) ===" % (и, попытка))
        items = рез.get("items") if isinstance(рез, dict) else рез
        if isinstance(рез, dict):
            print("  ключи: %s" % list(рез.keys()))
        if isinstance(items, list):
            for it in items:
                print("  [%s] %s | %s | ящик=%s | %s"
                      % (it.get("direction"), it.get("kind"),
                         str(it.get("ts"))[:19], it.get("mailbox_id"),
                         str(it.get("subject"))[:40]))
                тело = str(it.get("body") or "")
                print("       тело: %s" % (тело[:90].replace("\n", " ")
                                           if тело else "ПУСТО"))
        break
