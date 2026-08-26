# -*- coding: utf-8 -*-
"""Поставить ne_nash.py с ожиданием замка. Сверяем sha перед заменой."""
import hashlib
import io
import os
import py_compile
import shutil
import sys
import time

КАТИТЬ = "--katit" in sys.argv
БОЕВОЙ = r"C:\sender\sender\ne_nash.py"
НОВЫЙ = r"C:\sender\_ops\_novyy_ne_nash.py"
МЕТКА = "busy_timeout"

т = io.open(БОЕВОЙ, encoding="utf-8", errors="replace").read()
if МЕТКА in т:
    print("правка уже стоит")
    raise SystemExit(0)
нт = io.open(НОВЫЙ, encoding="utf-8", errors="replace").read()
if МЕТКА not in нт:
    raise SystemExit("в заготовке нет правки")
print("боевой %d знаков, заготовка %d" % (len(т), len(нт)))
print("sha боевого: %s" % hashlib.sha1(io.open(БОЕВОЙ, "rb").read()).hexdigest()[:12])
# Заготовка должна отличаться ТОЛЬКО вставкой: сверяем текст без неё.
без = нт.replace('''    # ЖДЁМ ЗАМОК. Базу делят панель, авто-отправка и разовые прогоны; 26.08
    # запись конкурента в реестр упала с «database is locked» ровно потому,
    # что рядом шёл разбор очереди. Реестр — решение оператора, терять его
    # из-за чужой транзакции нельзя.
    try:
        conn.execute("PRAGMA busy_timeout=60000")
    except sqlite3.Error:                                     # noqa: BLE001
        pass
''', "")
if без.strip() != т.strip():
    print("РАЗОШЛОСЬ: боевой отличается не только правкой — не трогаю")
    raise SystemExit(1)
print("боевой совпал с заготовкой без вставки")
if not КАТИТЬ:
    print("\nсухой прогон. Катить: --katit")
    raise SystemExit(0)
копия = "%s.bak-%d" % (БОЕВОЙ, int(time.time()))
shutil.copy2(БОЕВОЙ, копия)
shutil.copy2(НОВЫЙ, БОЕВОЙ)
py_compile.compile(БОЕВОЙ, doraise=True)
print("поставлен (.bak %s)" % os.path.basename(копия))
