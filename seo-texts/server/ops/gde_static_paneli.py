# -*- coding: utf-8 -*-
"""Откуда панель отдаёт собранный фронт и что там сейчас лежит.

Перед выкаткой dist надо знать точный каталог на сервере и хэши файлов -
чтобы не положить бандл мимо и не затереть чужое.
"""
import io
import os

for корень in (r"C:\sender\sender\web\dist", r"C:\sender\web\dist",
               r"C:\sender\dist"):
    есть = os.path.isdir(корень)
    print(f"{корень}: {'ЕСТЬ' if есть else 'нет'}")
    if есть:
        for путь, _, файлы in os.walk(корень):
            for ф in файлы:
                п = os.path.join(путь, ф)
                print(f"   {os.path.relpath(п, корень):<40} {os.path.getsize(п):>9}")

# чем служба запускается - там и путь до static_dir
for кандидат in (r"C:\sender\panel_service.py", r"C:\sender\run_panel.py",
                 r"C:\sender\serve.py", r"C:\sender\app.py"):
    if os.path.exists(кандидат):
        т = io.open(кандидат, encoding="utf-8", errors="replace").read()
        print(f"\n--- {кандидат} ---")
        for строка in т.splitlines():
            if "dist" in строка or "static" in строка or "site_app" in строка:
                print("   " + строка.strip()[:120])
