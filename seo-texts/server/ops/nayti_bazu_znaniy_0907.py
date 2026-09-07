# -*- coding: utf-8 -*-
"""Только чтение: где на сервере лежит база знаний по meyer. Важное в конце."""
import os

КОРНИ = [r"C:\sender", r"C:\Users", r"D:\\"]
ИНТЕРЕС = ("kb", "knowledge", "znani", "знани", "meyer", "мейер", "sort",
           "fotosep", "фотосеп", "сепарат", "separat", "рентген", "rentgen",
           "xray", "x-ray", "материал", "katalog", "каталог", "спецификац")
РАСШ = (".md", ".txt", ".docx", ".pdf", ".csv", ".html", ".xlsx", ".json")

папки, файлы_ = [], []
for корень in КОРНИ:
    if not os.path.isdir(корень):
        continue
    for путь, пп, фф in os.walk(корень):
        if путь.count(os.sep) - корень.count(os.sep) > 4:
            пп[:] = []
            continue
        пп[:] = [п for п in пп if п.lower() not in (
            "node_modules", ".git", "venv", "__pycache__", "windows",
            "appdata", "programdata", "$recycle.bin", "program files",
            "program files (x86)", "site-packages", "tests", "suppression")]
        имя = os.path.basename(путь).lower()
        if any(и in имя for и in ИНТЕРЕС):
            папки.append((путь, len(фф)))
        for ф in фф:
            н = ф.lower()
            if os.path.splitext(н)[1] in РАСШ and any(и in н for и in ИНТЕРЕС):
                try:
                    р = os.path.getsize(os.path.join(путь, ф))
                except OSError:
                    р = -1
                файлы_.append((os.path.join(путь, ф), р))

print("=== ПАПКИ ПО ИМЕНИ ===")
for п, n in папки[:30]:
    print("  %-70s файлов=%d" % (п[:70], n))
    try:
        for ф in sorted(os.listdir(п))[:10]:
            print("        %s" % ф)
    except OSError:
        pass

print("\n=== ФАЙЛЫ ПО ИМЕНИ (самые крупные) ===")
for п, р in sorted(файлы_, key=lambda x: -x[1])[:40]:
    print("  %9d  %s" % (р, п[:90]))
