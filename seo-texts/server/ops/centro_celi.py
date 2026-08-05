# -*- coding: utf-8 -*-
"""Цели обхода руководства по ЦЕНТРОБЕЖКЕ — 1597 предприятий, канал там не гонялся.

Обход руководства я пустил только по P25 (367 целей). Вторая база владельца
вчетверо больше и тем же каналом не проходилась ни разу. Порядок целей: сперва
те, у кого нет ни одного технического человека.
"""
import io, os, sqlite3, sys
from collections import Counter
sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB
ТЕХ = ('инженер','механик','энергетик','технич','производств','кипиа','метролог','технолог')
СНАБЖ = ('материально-техническ','снабжени','закупк','омтс','логистик','бухгалтер','склад')
ВЫХОД = r'C:\seostat\drop\drop-storage\centro-inns-dlya-rukovodstva.txt'
db = EDB.EnrichDB()
с_сайтом = {str(и) for и, in db.cx.execute(
    "SELECT inn FROM companies WHERE COALESCE(site,'')<>''")}
путь = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
цб = sqlite3.connect('file:' + путь + '?mode=ro', uri=True)
тех = set()
for и, поз in цб.execute("SELECT inn, COALESCE(position,'') FROM person"):
    н = str(поз).casefold()
    if any(x in н for x in ТЕХ) and not any(x in н for x in СНАБЖ):
        тех.add(str(и))
порядок = []
for и, сайт in цб.execute("SELECT inn, COALESCE(sayt,'') FROM company"):
    и = str(и)
    if not (str(сайт).strip() or и in с_сайтом):
        continue
    порядок.append((0 if и not in тех else 1, и))
цб.close()
порядок.sort()
with io.open(ВЫХОД, 'w', encoding='utf-8') as ф:
    ф.write('\n'.join(и for _, и in порядок) + '\n')
    ф.flush(); os.fsync(ф.fileno())
c = Counter(в for в, _ in порядок)
print('=== ЧИСЛА ===')
print(f'   целей всего                     {len(порядок):5}')
print(f'   без единого технаря (первыми)   {c[0]:5}')
print(f'   технарь уже есть                {c[1]:5}')
print(f'   файл: {os.path.basename(ВЫХОД)}')
