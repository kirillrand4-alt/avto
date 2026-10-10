# -*- coding: utf-8 -*-
r"""Перепроверка уже найденных сайтов по названию (10.10, полный прогон meyer7): правило sayt_po_nazvaniyu ко всем
«найден» журнала; домен, найденный для 2+ компаний, — отклонён у всех. Отклонённым дописывается запись «отклонён»
(последняя запись решает: отбор и сайты по названию снимут такой сайт из списка). Только журнал; список не трогает."""
import collections
import io
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import meyer_nalichie as MN  # noqa: E402
import sayt_po_nazvaniyu as SN  # noqa: E402

НАБОР = os.environ.get('KC_NABOR', 'meyer7')
ЖУРНАЛ = os.path.join(DIR, НАБОР + '-sayty-dobor.jsonl')
посл = {}
for s in io.open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
    try:
        з = json.loads(s)
    except ValueError:
        continue
    if з.get('inn'):
        посл[з['inn']] = з
сп = json.load(io.open(os.path.join(DIR, НАБОР + '-spisok.json'), encoding='utf-8'))['компании']
найд = {i: з for i, з in посл.items() if з.get('итог') == 'найден'}
частота = collections.Counter(MN.домен(з['сайт']) for з in найд.values())
лок = threading.Lock()
итог = collections.Counter()
причины = collections.Counter()


def одна(x):
    i, з = x
    имя = (сп.get(i) or {}).get('имя') or з.get('имя') or ''
    принят, почему = SN.проверить(имя, i, з['сайт'], частота[MN.домен(з['сайт'])] > 1)
    with лок:
        итог['принят' if принят else 'отклонён'] += 1
        if not принят:
            причины[почему.split(':')[0][:40]] += 1
            with io.open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
                f.write(json.dumps({'inn': i, 'итог': 'отклонён', 'сайт': з['сайт'], 'источник': з.get('источник', ''),
                                    'почему': почему, 'перепроверка': '10.10'}, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())


with ThreadPoolExecutor(16) as ex:
    list(ex.map(одна, найд.items()))
print('===ИТОГ===')
print(json.dumps({'найдено было': len(найд), 'итог': итог, 'причины': причины}, ensure_ascii=False, indent=1))
