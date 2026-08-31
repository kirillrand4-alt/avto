# -*- coding: utf-8 -*-
"""Запасная модель линз — соннет, а не опус (команда владельца 31.08).

Клиент линз после трёх подряд отказов переключается на LENS_FALLBACK_MODEL и
назад уже не возвращается. По умолчанию там стоял claude-opus-4-7, которого
шлюз сейчас не отдаёт: гейт покупателя уходил на него и умирал целиком —
«стрим молчит 102 с». Ставим соннет: он же и основная модель проверок,
переключаться будет некуда, и линза останется на рабочей модели.
Переменная LENS_FALLBACK_MODEL продолжает работать и переопределяет это.
"""
import io
import os
import py_compile
import sys
import time

ФАЙЛ = r"C:\sender\sender\review_lenses.py"
ПРИМЕНИТЬ = "--primenit" in sys.argv
СТАРО = "    fallback = os.environ.get('LENS_FALLBACK_MODEL', 'claude-opus-4-7')"
НОВО = ("    # ЗАПАСНАЯ — СОННЕТ (владелец 31.08: «оставь только соннет»).\n"
        "    # Здесь стоял claude-opus-4-7, и 31.08 это положило гейт\n"
        "    # покупателя целиком: шлюз перестал отдавать эту модель, три\n"
        "    # таймаута переводили линзу на неё, а назад возврата нет — все\n"
        "    # восемь попыток умирали с «стрим молчит 102 с». Соннет и так\n"
        "    # основная модель проверок, поэтому переключаться некуда и\n"
        "    # эскалация перестаёт быть точкой отказа.\n"
        "    fallback = os.environ.get('LENS_FALLBACK_MODEL', "
        "'claude-sonnet-4-6')")

т = io.open(ФАЙЛ, encoding="utf-8").read()
n = т.count(СТАРО)
print("файл: %d Б, строк %d; якорь встречается %d раз"
      % (len(т.encode("utf-8")), len(т.splitlines()), n))
print("сейчас в файле: %s"
      % [с.strip() for с in т.splitlines() if "LENS_FALLBACK_MODEL" in с])
if n != 1:
    print("якорь не единственный — не трогаю")
    raise SystemExit(1)
if not ПРИМЕНИТЬ:
    print("\n[сухой прогон] применить — с ключом --primenit")
    raise SystemExit(0)

запас = "%s.bak-%d" % (ФАЙЛ, int(time.time()))
io.open(запас, "w", encoding="utf-8").write(т)
with io.open(ФАЙЛ, "w", encoding="utf-8") as f:
    f.write(т.replace(СТАРО, НОВО, 1))
    f.flush()
    os.fsync(f.fileno())
try:
    py_compile.compile(ФАЙЛ, doraise=True)
    print("бэкап: %s\npy_compile: ок" % запас)
except Exception as e:                                        # noqa: BLE001
    io.open(ФАЙЛ, "w", encoding="utf-8").write(т)
    print("КОМПИЛЯЦИЯ УПАЛА, откатил: %s" % str(e)[:200])
    raise SystemExit(1)
т2 = io.open(ФАЙЛ, encoding="utf-8").read()
print("\n=== ИТОГ ===")
print("стало: %s" % [с.strip() for с in т2.splitlines()
                     if "LENS_FALLBACK_MODEL" in с])
