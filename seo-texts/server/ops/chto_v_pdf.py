# -*- coding: utf-8 -*-
"""Что за каталог прислал владелец: страницы, текст первых страниц, объём."""
import glob
import os
import subprocess
import sys

п = glob.glob(r"C:\sender\_ops\belarus\*.pdf")
if not п:
    print("PDF не найден")
    sys.exit(1)
файл = п[0]
print("файл: %s (%.1f МБ)" % (os.path.basename(файл),
                              os.path.getsize(файл) / 1048576.0))
try:
    import pypdf
    чтец = pypdf.PdfReader(файл)
    print("страниц: %d" % len(чтец.pages))
    for н in (0, 1, 2):
        if н >= len(чтец.pages):
            break
        т = " ".join((чтец.pages[н].extract_text() or "").split())
        print("\n--- страница %d ---\n%s" % (н + 1, т[:900]))
except ImportError:
    print("pypdf нет, ставлю...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pypdf", "-q"],
                   capture_output=True, timeout=300)
    import pypdf
    чтец = pypdf.PdfReader(файл)
    print("страниц: %d" % len(чтец.pages))
    т = " ".join((чтец.pages[0].extract_text() or "").split())
    print("\n--- страница 1 ---\n%s" % т[:900])
