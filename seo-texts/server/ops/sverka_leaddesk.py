# -*- coding: utf-8 -*-
"""Почему не сошёлся якорь: чем leaddesk.py на сервере отличается от репо."""
import io

ФАЙЛ = r"C:\sender\sender\leaddesk.py"
т = io.open(ФАЙЛ, encoding="utf-8").read()
print("файл %d байт, строк %d" % (len(т), len(т.splitlines())))
print("")
print("--- место вокруг create_lead / Bitrix ---")
строки = т.splitlines()
for н, с in enumerate(строки, 1):
    if "bitrix" in с.lower() or "created" in с or "push_warm_lead" in с:
        низ = max(0, н - 3)
        for i in range(низ, min(len(строки), н + 3)):
            print("   %4d | %s" % (i + 1, строки[i][:100]))
        print("   ---")
