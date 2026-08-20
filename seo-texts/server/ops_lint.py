# -*- coding: utf-8 -*-
"""Проверить ops-скрипты на неопределённые имена ДО отправки на сервер.

Зачем отдельная проверка. Скрипты из ops/ импортируют sender.* — пакет
живёт на сервере (C:\\sender), локально его нет, поэтому импортом их не
проверить, а `python -m py_compile` ловит только синтаксис. Забытый
импорт синтаксически безупречен и падает уже на сервере, посреди
оплаченного прогона: так трижды подряд и вышло — `re`, `_в_журнал`,
`минус_класс` (последний уронил замер партии на первом же окне).

pyflakes читает файл статически и видит имя, которое нигде не связано,
не выполняя ни строчки. Запуск: python3 ops_lint.py [файл ...]
Без аргументов — весь каталог ops/.
"""
import os
import sys

try:
    from pyflakes.api import checkPath
    from pyflakes.reporter import Reporter
except ImportError:                                           # noqa: BLE001
    print("нет pyflakes: pip install pyflakes")
    raise SystemExit(2)

корень = os.path.dirname(os.path.abspath(__file__))
цели = sys.argv[1:] or sorted(
    os.path.join(корень, "ops", и)
    for и in os.listdir(os.path.join(корень, "ops")) if и.endswith(".py"))

# Только неопределённые имена: остальное в ops-скриптах — шум (они
# намеренно одноразовые, с неиспользованными импортами и длинными строками).
плохо = 0
for путь in цели:
    import io as _io
    буф_о, буф_э = _io.StringIO(), _io.StringIO()
    checkPath(путь, Reporter(буф_о, буф_э))
    строки = [с for с in (буф_о.getvalue() + буф_э.getvalue()).splitlines()
              if "undefined name" in с or "syntax" in с.lower()]
    if строки:
        плохо += 1
        for с in строки:
            print(с)
print(f"проверено {len(цели)}, с неопределёнными именами: {плохо}")
raise SystemExit(1 if плохо else 0)
