# -*- coding: utf-8 -*-
"""Структура выгрузки сделок с дропа (json/csv): ключи, примеры, значения полей стадии/причины. Только чтение.
    sdelki_vse_struktura.py <имя_на_дропе>"""
import csv, io, json, sys
from collections import Counter
п = r"C:\seostat\drop\drop-storage" + "\\" + sys.argv[1]
if п.endswith(".zip"):
    import zipfile
    z = zipfile.ZipFile(п)
    for i in z.infolist()[:20]: print(i.filename, i.file_size)
    for i in z.infolist():
        if i.filename.lower().endswith((".csv", ".txt", ".xls")):
            сыр = z.read(i.filename)[:20000]
            for кд in ("utf-8-sig", "cp1251"):
                try: т = сыр.decode(кд); break
                except Exception: continue
            import re as _re, html as _h
            т = z.read(i.filename)[:400000].decode("utf-8", "replace")
            ряды = _re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", т)
            ячейки = lambda р: [_h.unescape(_re.sub(r"<[^>]+>", "", x)).strip() for x in _re.findall(r"(?is)<t[hd][^>]*>(.*?)</t[hd]>", р)]
            шапка = ячейки(ряды[0]); print("колонок:", len(шапка)); print(шапка)
            for р in ряды[1:3]: print({шапка[k]: v[:50] for k, v in enumerate(ячейки(р)) if v and k < len(шапка)})
            break
elif п.endswith(".json"):
    д = json.load(io.open(п, encoding="utf-8"))
    print("тип:", type(д).__name__, "длина:", len(д))
    эл = list(д.values())[:2] if isinstance(д, dict) else д[:2]
    for x in эл: print(json.dumps(x, ensure_ascii=False)[:900])
else:
    r = csv.reader(io.open(п, encoding="utf-8-sig", errors="replace"), delimiter=";")
    шапка = next(r); print("колонки:", len(шапка)); print(шапка)
    стр = [next(r) for _ in range(3)]
    for s in стр: print({шапка[i]: s[i][:60] for i in range(min(len(шапка), len(s))) if s[i]})
