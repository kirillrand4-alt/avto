# -*- coding: utf-8 -*-
"""Только чтение: как устроен заслон по спам-отказам и вернёт ли он паузу."""
import io
import re
import sys

стр = io.open(r"C:\sender\sender\gates.py", encoding="utf-8",
              errors="replace").read().splitlines()
for имя in ("check_otkaz_vsego", "check_mailbox_otkaz"):
    н = [i for i, x in enumerate(стр) if re.search(r"def %s" % имя, x)]
    for i in н:
        print("=== gates.py: %s (строка %d) ===" % (имя, i + 1))
        отступ = len(стр[i]) - len(стр[i].lstrip())
        for j in range(i, min(i + 40, len(стр))):
            x = стр[j]
            if j > i and x.strip() and (len(x) - len(x.lstrip())) <= отступ \
                    and x.lstrip().startswith("def "):
                break
            print("  %4d  %s" % (j + 1, x[:106]))
        print()

print("=== ИТОГ: ЧТО ГОВОРЯТ ГЕЙТЫ ПРЯМО СЕЙЧАС ===")
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402
import sender.gates as G          # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
g = G.Gates(cfg, store)
for имя in ("check_global", "check_otkaz_vsego"):
    try:
        d = getattr(g, имя)()
        print("  %-20s tripped=%s | %s" % (имя, getattr(d, "tripped", "?"),
                                           str(getattr(d, "reason", ""))[:80]))
    except Exception as ex:
        print("  %-20s ошибка %s" % (имя, str(ex)[:60]))
for m in ("a.miroshnichenko@optic-sort.ru", "i.kuznetsova@sort-systems.ru"):
    try:
        d = g.check_mailbox_otkaz(m)
        print("  otkaz %-34s tripped=%s | %s"
              % (m[:34], getattr(d, "tripped", "?"), str(getattr(d, "reason", ""))[:60]))
    except Exception as ex:
        print("  otkaz %-34s ошибка %s" % (m[:34], str(ex)[:50]))
