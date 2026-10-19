# -*- coding: utf-8 -*-
"""КЦ 19.10: гейт «название компании в теме КЦ» отменён для тем с названием в
«ёлочках» (канон 23 их требует). Бэкап .bak-kc1910b-*."""
import io, py_compile, shutil, sys, time
П = r"C:\sender\sender\ai_letter.py"
т = io.open(П, encoding="utf-8").read()
С = "        elif not _по_мейеру and ('«' in subject) or (not _по_мейеру and _имя_фирмы and короткое_имя(_имя_фирмы)\n"
Н = "        elif not (_по_мейеру or _с_назв) and ('«' in subject) or (not (_по_мейеру or _с_назв) and _имя_фирмы and короткое_имя(_имя_фирмы)\n"
if Н in т: print("=== КЦ 1910b: УЖЕ БЫЛО ==="); sys.exit()
if т.count(С) != 1: print("якорь:", т.count(С)); print("=== КЦ 1910b: НЕ ПРИМЕНЕНО ==="); sys.exit()
б = П + ".bak-kc1910b-%d" % int(time.time()); shutil.copy2(П, б)
io.open(П, "w", encoding="utf-8").write(т.replace(С, Н))
try: py_compile.compile(П, doraise=True)
except Exception as е: shutil.copy2(б, П); print("откат:", е); sys.exit()
print("бэкап:", б); print("=== КЦ 1910b: ПРИМЕНЕНО ===")
