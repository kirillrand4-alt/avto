# -*- coding: utf-8 -*-
"""Выкатить ai_letter.py и ai_quota.py из подготовленных копий в _ops.

Сверка перед подменой: серверная версия должна быть той, от которой правка
делалась (иначе рядом поработала соседняя сессия и класть целиком нельзя).
"""
import hashlib
import io
import os
import py_compile
import shutil
import time

# хэши серверных файлов, от которых делалась правка
ОЖИДАЕМ = {
    "ai_letter.py": "3b7c6e10476f",
    "ai_quota.py": "6faafbc2224f",
}
МЕТКА = {"ai_letter.py": "ВЗГЛЯД ТРЕТИЙ",
         "ai_quota.py": "_perestavit_napravlenie"}

for имя, ожид in ОЖИДАЕМ.items():
    цель = os.path.join(r"C:\sender\sender", имя)
    новый = os.path.join(r"C:\sender\_ops", "_novyy_" + имя)
    if not os.path.exists(новый):
        print("%s: нет подготовленной копии %s" % (имя, новый))
        continue
    было = io.open(цель, "rb").read()
    факт = hashlib.sha256(было).hexdigest()[:12]
    if факт != ожид:
        print("%s: СЕРВЕРНАЯ ВЕРСИЯ НЕ ТА (%s вместо %s) — не трогаю"
              % (имя, факт, ожид))
        continue
    новое = io.open(новый, "rb").read()
    if МЕТКА[имя] not in новое.decode("utf-8", "replace"):
        print("%s: в новой копии нет метки %r — не трогаю" % (имя, МЕТКА[имя]))
        continue
    бэк = цель + ".bak-%d" % int(time.time())
    shutil.copy2(цель, бэк)
    with io.open(цель, "wb") as f:
        f.write(новое)
        f.flush()
        os.fsync(f.fileno())
    try:
        py_compile.compile(цель, doraise=True)
    except Exception as e:                                       # noqa: BLE001
        shutil.copy2(бэк, цель)
        print("%s: НЕ КОМПИЛИРУЕТСЯ, откатил: %s" % (имя, str(e)[:120]))
        continue
    print("%s: %d -> %d байт, бэкап %s"
          % (имя, len(было), len(новое), os.path.basename(бэк)))
