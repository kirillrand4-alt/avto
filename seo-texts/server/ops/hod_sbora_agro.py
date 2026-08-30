# -*- coding: utf-8 -*-
"""Ход сбора по агро-кодам."""
import io, os, time
ЛОГ = r"C:\sender\_ops\sbor-agro.log"
CSV = r"C:\seostat\Parser2\data\agro-base.csv"
if os.path.exists(ЛОГ):
    т = io.open(ЛОГ, encoding="utf-8", errors="ignore").read()
    print("лог %d б, изменён %s"
          % (len(т), time.strftime("%H:%M:%S",
                                   time.localtime(os.path.getmtime(ЛОГ)))))
    print(т[-1400:])
else:
    print("лога ещё нет")
if os.path.exists(CSV):
    n = sum(1 for _ in io.open(CSV, encoding="utf-8", errors="ignore"))
    print("\nCSV: %d строк, %.2f МБ, изменён %s"
          % (n, os.path.getsize(CSV) / 1048576,
             time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(CSV)))))
else:
    print("\nCSV ещё не создан")
print("сейчас %s" % time.strftime("%H:%M:%S"))
