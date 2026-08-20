# -*- coding: utf-8 -*-
"""Хирургически вшить переключатель одной двери в боевой gen_provider.py.

Каталог общий с соседней сессией, и её копия местами свежее моей (там,
например, уже поправлена опечатка, которая у меня ещё была). Поэтому файл
целиком НЕ перезаписываем — вставляем только свои шесть строк.
"""
import hashlib
import io
import shutil
import time

ФАЙЛ = r"C:\sender\gen_provider.py"
ЯКОРЬ = ("         'veo', 'kimi', 'moonshot', 'mistral', 'glm'))\n")
ВСТАВКА = (
    "    # У ДРУГОГО ШЛЮЗА ДВЕРЬ МОЖЕТ БЫТЬ ОДНА. baza-ai отдаёт клодовские\n"
    "    # модели тоже по /v1/chat/completions, а /v1/messages у него 404 —\n"
    "    # правило «клод значит anthropic-дверь» там ломает всё. Переключатель,\n"
    "    # а не автоугадайка: шлюзов много, и молча менять дверь по имени хоста\n"
    "    # опаснее, чем попросить.\n"
    "    if str(os.environ.get('PROVIDER_OPENAI_ONLY', '')).strip().lower() in (\n"
    "            '1', 'true', 'yes', 'да'):\n"
    "        po_anthropic = False\n")

s = io.open(ФАЙЛ, encoding="utf-8").read()
if "PROVIDER_OPENAI_ONLY" in s:
    print("переключатель уже вшит — ничего не делаю")
    raise SystemExit(0)
if s.count(ЯКОРЬ) != 1:
    print(f"якорь найден {s.count(ЯКОРЬ)} раз — не трогаю")
    raise SystemExit(2)
рез = ФАЙЛ + ".bak-" + time.strftime("%m%d-%H%M")
shutil.copy2(ФАЙЛ, рез)
io.open(ФАЙЛ, "w", encoding="utf-8").write(s.replace(ЯКОРЬ, ЯКОРЬ + ВСТАВКА))
print("бэкап:", рез)
print("sha после:", hashlib.sha256(
    io.open(ФАЙЛ, "rb").read()).hexdigest()[:16])
import py_compile                                              # noqa: E402
py_compile.compile(ФАЙЛ, doraise=True)
print("компилируется")
