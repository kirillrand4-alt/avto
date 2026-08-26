# -*- coding: utf-8 -*-
"""Поставить правленые probe_enrich/probe_sync на боевой sender/.

Заменяем ЦЕЛИКОМ, но только убедившись, что серверная копия побайтно равна
той, от которой мы правили: каталог делят несколько сессий, и молча затирать
чужую работу нельзя. Не совпало — выходим и жалуемся.

    python vykatit_probe_pravki.py            # сверить
    python vykatit_probe_pravki.py --katit    # поставить
"""
import hashlib
import io
import os
import py_compile
import shutil
import sys
import time

КАТИТЬ = "--katit" in sys.argv
# sha1 копий, от которых правили (ветка claude/partiya-935-generation-p0zysk)
ОЖИДАЕМ = {
    r"C:\sender\sender\probe_enrich.py":
        ("6ee56f1cd70a7d8a5d9a81ed55c1b3b02031a21f",
         r"C:\sender\_ops\_novyy_probe_enrich.py", "ЖДЁМ ЗАМОК"),
    r"C:\sender\sender\probe_sync.py":
        ("cc062d75b17d78e3f3823d46f0f0482bf5c691a8",
         r"C:\sender\_ops\_novyy_probe_sync.py", "ПОД ЗАМКОМ STORE"),
}

к_замене = []
for боевой, (ожид, новый, метка) in ОЖИДАЕМ.items():
    есть = hashlib.sha1(io.open(боевой, "rb").read()).hexdigest()
    т = io.open(боевой, encoding="utf-8", errors="replace").read()
    if метка in т:
        print("%-22s правка уже стоит" % os.path.basename(боевой))
        continue
    if есть != ожид:
        print("%-22s РАЗОШЛОСЬ: на сервере %s, ждали %s — не трогаю"
              % (os.path.basename(боевой), есть[:12], ожид[:12]))
        continue
    if not os.path.exists(новый):
        print("%-22s нет заготовки %s" % (os.path.basename(боевой), новый))
        continue
    нт = io.open(новый, encoding="utf-8", errors="replace").read()
    if метка not in нт:
        print("%-22s в заготовке нет правки — не трогаю" % os.path.basename(боевой))
        continue
    print("%-22s совпал, заготовка на месте (%d -> %d знаков)"
          % (os.path.basename(боевой), len(т), len(нт)))
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
print("готово: %d файлов" % len(к_замене))
