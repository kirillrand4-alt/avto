# -*- coding: utf-8 -*-
"""Как идёт обход сайтов ProdExpo."""
import glob, io, json, os, time
кат = r"C:\sender\_ops"
логи = sorted(glob.glob(os.path.join(кат, "belarus_kartochki-*.log")))
for п in логи[-2:]:
    print("==== %s (%.0f мин назад) ====" % (os.path.basename(п),
                                             (time.time() - os.path.getmtime(п)) / 60))
    for с in io.open(п, encoding="utf-8", errors="replace").read().splitlines()[-10:]:
        print("   " + с[:170])
for п in sorted(glob.glob(os.path.join(кат, "belarus_kartochki-*.err")))[-1:]:
    т = io.open(п, encoding="utf-8", errors="replace").read().strip()
    if т:
        print("==== ошибки ====")
        print(т[-800:])
ф = r"C:\sender\_ops\belarus\kartochki.jsonl"
if os.path.exists(ф):
    n = сайт = унп = почта = текст = 0
    for с in io.open(ф, encoding="utf-8", errors="replace"):
        try:
            d = json.loads(с)
        except Exception:
            continue
        n += 1
        сайт += 1 if d.get("сайт") else 0
        унп += 1 if d.get("унп") else 0
        почта += 1 if d.get("почта") else 0
        текст += 1 if d.get("текст_сайта") else 0
    print("")
    print("карточек: %d | с сайтом %d | с УНП %d | с почтой %d | с текстом сайта %d"
          % (n, сайт, унп, почта, текст))
else:
    print("kartochki.jsonl ещё нет")
