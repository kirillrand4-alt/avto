# -*- coding: utf-8 -*-
"""Только чтение: в какую сторону движок согласует род отправителя и
есть ли правило про заглавное «Вы»."""
import inspect
import re
import sys

sys.path.insert(0, r"C:\sender")
import sender.gender_agree as GA  # noqa: E402

print("=== функции gender_agree ===")
for имя in dir(GA):
    о = getattr(GA, имя)
    if callable(о) and not имя.startswith("_"):
        try:
            print("  %-26s %s" % (имя, str(inspect.signature(о))[:90]))
        except Exception:
            pass

т = inspect.getsource(GA)
print("\n=== направление согласования (док) ===")
for м in re.finditer(r"(мужск|женск|masc|fem)", т):
    н = т[:м.start()].count("\n")
    с = т.splitlines()[н].strip()
    if с and not с.startswith(('"', "'")):
        print("  %d| %s" % (н + 1, с[:104]))

print("\n=== ПРОБА НА ЖИВОЙ ФРАЗЕ ===")
ф = None
for имя in ("soglasovat", "soglasuy", "agree", "primenit", "prevesti"):
    for a in dir(GA):
        if a.lower().startswith(имя):
            ф = getattr(GA, a)
            break
    if ф:
        break
print("  функция: %s" % (getattr(ф, "__name__", None)))
проба = ("Готов разобрать ваши задачи и найти решение.\n\n"
         "Я был среди спикеров, решил написать.")
if ф:
    for имя_отпр in ("Ирина Кузнецова", "Артем Тюнин"):
        try:
            рез = ф(проба, имя_отпр)
        except TypeError:
            try:
                рез = ф(проба, имя=имя_отпр)
            except Exception as ex:
                рез = "ошибка: %s" % str(ex)[:90]
        print("  %-18s -> %s" % (имя_отпр, str(рез).replace("\n", " ")[:140]))

print("\n=== ПРАВИЛО ПРО ЗАГЛАВНОЕ «ВЫ» В ГЕЙТЕ ===")
import sender.ai_letter as A  # noqa: E402
та = inspect.getsource(A)
найдено = 0
for м in re.finditer(r"Вы[ае]?ш|«Вы»|заглавн", та):
    н = та[:м.start()].count("\n")
    с = та.splitlines()[н].strip()
    if any(k in с for k in ("fails", "re.search", "if ", "ЗАПРЕТ", "нельзя")):
        print("  %d| %s" % (н + 1, с[:104]))
        найдено += 1
print("  упоминаний-правил: %d" % найдено)
