# -*- coding: utf-8 -*-
"""Совпадает ли серверный _ops/partiya_gen.py с репозиторным. Не перезаписываем."""
import hashlib
import io
import os
import time

п = r"C:\sender\_ops\partiya_gen.py"
print("файл: %s" % ("есть" if os.path.exists(п) else "НЕТ"))
if os.path.exists(п):
    т = io.open(п, encoding="utf-8", errors="replace").read()
    print("размер %d Б, изменён %s, sha1 %s"
          % (os.path.getsize(п),
             time.strftime("%d.%m %H:%M", time.localtime(os.path.getmtime(п))),
             hashlib.sha1(т.encode("utf-8")).hexdigest()[:12]))
    print("строк: %d" % len(т.splitlines()))
    for с in т.splitlines():
        if с.startswith("МОДЕЛЬ = os.environ") or с.startswith("ГРУППА =") \
                or с.startswith("ЖУРНАЛ ="):
            print("   %s" % с[:110])
print("\nчто ещё лежит в _ops (питон, свежие сверху):")
файлы = [(os.path.getmtime(os.path.join(r"C:\sender\_ops", f)), f)
         for f in os.listdir(r"C:\sender\_ops") if f.endswith(".py")]
for т_, f in sorted(файлы, reverse=True)[:12]:
    print("   %-38s %s" % (f, time.strftime("%d.%m %H:%M", time.localtime(т_))))
