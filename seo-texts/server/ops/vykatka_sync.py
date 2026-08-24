# -*- coding: utf-8 -*-
"""Выкатить probe_sync.py: боевой совпал с репозиторием побайтно (b7fae186fd9a),
поэтому кладём целиком, с копией и проверкой компиляции."""
import hashlib
import io
import os
import py_compile
import shutil
import time

путь = r"C:\sender\sender\probe_sync.py"
новый = r"C:\sender\_ops\probe_sync.py.new"
текущий = io.open(путь, "rb").read()
print("боевой md5=%s" % hashlib.md5(текущий).hexdigest()[:12])
if hashlib.md5(текущий).hexdigest()[:12] != "b7fae186fd9a":
    print("НЕ ВЫКАТЫВАЕМ: боевой файл разошёлся с ожидаемым")
    raise SystemExit(1)
т = io.open(новый, encoding="utf-8").read()
копия = путь + ".bak-%d" % int(time.time())
shutil.copy2(путь, копия)
io.open(путь, "w", encoding="utf-8", newline="").write(т)
try:
    py_compile.compile(путь, doraise=True)
    assert 'for статус in ("approved", "pending")' in т
    print("легло, компиляция ОК, копия %s" % os.path.basename(копия))
except Exception as e:  # noqa: BLE001
    shutil.copy2(копия, путь)
    print("ОТКАТ: %s" % e)
