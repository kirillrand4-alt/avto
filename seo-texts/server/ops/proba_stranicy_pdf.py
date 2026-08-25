# -*- coding: utf-8 -*-
"""Каталог оказался сканом: текста в PDF нет. Проверяем путь «страница ->
картинка -> модель» на одной странице, прежде чем гнать все девяносто.
"""
import glob
import os
import subprocess
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ставлю PyMuPDF...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pymupdf", "-q"],
                   capture_output=True, timeout=600)
    import fitz

файл = glob.glob(r"C:\sender\_ops\belarus\*.pdf")[0]
КАРТИНКИ = r"C:\sender\_ops\belarus\pages"
os.makedirs(КАРТИНКИ, exist_ok=True)
док = fitz.open(файл)
print("страниц: %d" % док.page_count)

# Одна страница из середины: обложку и оглавление смотреть смысла нет.
for н in (4, 20, 45):
    if н >= док.page_count:
        continue
    стр = док.load_page(н)
    текст = " ".join((стр.get_text() or "").split())
    пикс = стр.get_pixmap(dpi=150)
    п = os.path.join(КАРТИНКИ, "p%03d.png" % (н + 1))
    пикс.save(п)
    print("\nстраница %d: текстовый слой %d знаков, картинка %d б (%dx%d)"
          % (н + 1, len(текст), os.path.getsize(п), пикс.width, пикс.height))
    if текст:
        print("   текст: %s" % текст[:300])
    print("   картинок на странице: %d" % len(стр.get_images(full=True)))
