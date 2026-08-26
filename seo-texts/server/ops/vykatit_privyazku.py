# -*- coding: utf-8 -*-
"""Поставить привязку ответа по домену: imap_watcher + store.

Заменяем целиком, убедившись, что каждая строка боевой копии есть в
заготовке — иначе соседняя сессия что-то дописала, и замена это затрёт.
"""
import io
import os
import py_compile
import shutil
import sys
import time

КАТИТЬ = "--katit" in sys.argv
ПАРЫ = (
    (r"C:\sender\sender\imap_watcher.py", r"C:\sender\_ops\_novyy_imap_watcher.py",
     "_recipient_by_domain"),
    (r"C:\sender\sender\store.py", r"C:\sender\_ops\_novyy_store.py",
     "recipients_by_domain"),
)
к_замене = []
for боевой, новый, метка in ПАРЫ:
    имя = os.path.basename(боевой)
    т = io.open(боевой, encoding="utf-8", errors="replace").read()
    нт = io.open(новый, encoding="utf-8", errors="replace").read()
    if метка in т:
        print("%-20s правка уже стоит" % имя)
        continue
    if метка not in нт:
        print("%-20s в заготовке нет правки — пропуск" % имя)
        continue
    свои = set(нт.splitlines())
    пропало = [с for с in т.splitlines() if с.strip() and с not in свои]
    if пропало:
        print("%-20s ЗАТРЁМ %d строк — не трогаю:" % (имя, len(пропало)))
        for с in пропало[:8]:
            print("     " + с[:130])
        continue
    print("%-20s боевой целиком в заготовке (%d -> %d знаков)"
          % (имя, len(т), len(нт)))
    к_замене.append((боевой, новый))

if not КАТИТЬ:
    print("\nсухой прогон, к замене: %d. Катить: --katit" % len(к_замене))
    raise SystemExit(0)
for боевой, новый in к_замене:
    копия = "%s.bak-%d" % (боевой, int(time.time()))
    shutil.copy2(боевой, копия)
    shutil.copy2(новый, боевой)
    py_compile.compile(боевой, doraise=True)
    print("поставлен %s (.bak %s)" % (os.path.basename(боевой),
                                      os.path.basename(копия)))
