# -*- coding: utf-8 -*-
"""Только чтение: готовность каждого ящика глазами самой панели."""
import inspect
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config    # noqa: E402
from sender.store import Store      # noqa: E402
import sender.sender as S           # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

кл = None
for имя in dir(S):
    o = getattr(S, имя)
    if inspect.isclass(o) and any("readiness" in m.lower() for m in dir(o)):
        кл = o
        break
print("=== класс с проверкой готовности: %s ===" % (кл.__name__ if кл else "не найден"))
if кл:
    методы = [m for m in dir(кл) if "readiness" in m.lower() or "ready" in m.lower()]
    print("  методы:", методы)

НОВЫЕ = ("food-sort.ru", "sorting-systems", "rentgen-control", "optical-sort",
         "rentgen-inspec", "inspection-syst")
try:
    snd = кл(cfg, store)
except Exception as ex:
    try:
        snd = кл(cfg, store, None)
    except Exception as ex2:
        print("  не создался: %s | %s" % (str(ex)[:70], str(ex2)[:70]))
        snd = None

if snd:
    м = None
    for имя in ("readiness", "mailbox_readiness", "_readiness"):
        if hasattr(snd, имя):
            м = getattr(snd, имя)
            break
    строки = []
    for mb in cfg.mailboxes():
        mid = mb.mailbox_id
        нов = any(x in mid for x in НОВЫЕ)
        try:
            r = м(mid)
            строки.append((нов, mid, getattr(r, "ready", None), getattr(r, "ramp_day", None),
                           getattr(r, "daily_limit", None), getattr(r, "sent_today", None),
                           ",".join(getattr(r, "reasons", ()) or ())))
        except Exception as ex:
            строки.append((нов, mid, "ОШИБКА", "", "", "", str(ex)[:50]))

    for метка, наб in (("СТАРЫЕ", False), ("НОВЫЕ (заведены вчера)", True)):
        print("\n=== %s ===" % метка)
        print("  %-40s %6s %5s %6s %6s  %s"
              % ("ящик", "готов", "рамп", "лимит", "сегодня", "причины"))
        for нов, mid, ready, rd, dl, st, rs in строки:
            if нов != наб:
                continue
            print("  %-40s %6s %5s %6s %6s  %s"
                  % (mid[:40], ready, rd, dl, st, rs))

print("\n=== ИТОГ ===")
print("  сравни колонки «рамп» и «лимит» у новых и старых")
