# -*- coding: utf-8 -*-
"""Хвост лога прогона «Россия 9000» после последнего запуска."""
import io
import os
import time
т = io.open(r"C:\sender\_ops\gen-rossiya-9000.log", encoding="utf-8",
            errors="replace").read()
с = т.rsplit("==== ЗАПУСК", 1)
кусок = "==== ЗАПУСК" + с[-1] if len(с) > 1 else т
строки = кусок.splitlines()
print("строк после запуска: %d, лог обновлялся %d с назад"
      % (len(строки), time.time() - os.path.getmtime(
          r"C:\sender\_ops\gen-rossiya-9000.log")))
for л in строки[:12]:
    print("   " + л[:170])
print("   ...")
for л in строки[-22:]:
    print("   " + л[:170])
print("=== ЛОГ 9000 ===")
