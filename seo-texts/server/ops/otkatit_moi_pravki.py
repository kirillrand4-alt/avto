# -*- coding: utf-8 -*-
"""Откатить мои правки: ai_quota.py из бэкапа. Сводка в конце."""
import glob
import io
import os
import py_compile
import shutil
import time

П = r"C:\sender\sender\ai_quota.py"
бэкапы = sorted(glob.glob(П + ".bak-*"))
шаги = []

т = io.open(П, encoding="utf-8", errors="replace").read()
было_моё = "_IDEA_LENSES_ZERNO" in т

if not было_моё:
    шаги.append("правки в ai_quota.py уже нет — откатывать нечего")
elif not бэкапы:
    шаги.append("БЭКАПОВ НЕТ — откатить нечем, не трогаю")
else:
    мой = бэкапы[-1]
    б = io.open(мой, encoding="utf-8", errors="replace").read()
    if "_IDEA_LENSES_ZERNO" in б:
        шаги.append("в свежем бэкапе тоже есть правка — беру предыдущий")
        мой = бэкапы[-2] if len(бэкапы) > 1 else None
    if мой:
        страховка = П + ".pered-otkatom-%d" % int(time.time())
        shutil.copy2(П, страховка)
        shutil.copy2(мой, П)
        try:
            py_compile.compile(П, doraise=True)
            шаги.append("откачено из %s, компилируется" % os.path.basename(мой))
            шаги.append("снимок перед откатом: %s" % os.path.basename(страховка))
        except Exception as ex:                                # noqa: BLE001
            shutil.copy2(страховка, П)
            шаги.append("бэкап не компилируется (%s) — вернул как было"
                        % str(ex)[:70])
    else:
        шаги.append("подходящего бэкапа не нашлось")

после = io.open(П, encoding="utf-8", errors="replace").read()

print("=" * 76)
print("=== СВОДКА: ОТКАТ ПРАВОК ===")
print("бэкапов ai_quota.py: %d" % len(бэкапы))
for б in бэкапы[-4:]:
    print("   %s  %d Б" % (os.path.basename(б), os.path.getsize(б)))
print("")
for с in шаги:
    print("   " + с)
print("")
print("правка _IDEA_LENSES_ZERNO в файле: %s"
      % ("ЕСТЬ" if "_IDEA_LENSES_ZERNO" in после else "нет, откачено"))
print("размер файла: %d Б" % len(после))
