# -*- coding: utf-8 -*-
"""Три канала разом — состояние по ПОТОКАМ, не по счётчикам лога."""
import io, json, os, time
from collections import Counter
потоки = {
    'обход руководства, центробежка': r'C:\seostat\drop\centro_leadership_stream.jsonl',
    'ЕИС-протоколы':                  r'C:\seostat\drop\eis_protocols_stream.jsonl',
    'разбор корпуса провайдером':     r'C:\seostat\drop\tp_korpus_razbor.jsonl',
}
print('=== ЧИСЛА ===')
for имя, п in потоки.items():
    if not os.path.exists(п):
        print(f'   {имя:34} ФАЙЛА НЕТ (ещё не писал)')
        continue
    n = люд = осш = 0
    for s in io.open(п, encoding='utf-8', errors='replace'):
        s = s.strip()
        if not s:
            continue
        n += 1
        try:
            з = json.loads(s)
        except Exception:
            continue
        осш += 1 if з.get('err') else 0
        л = з.get('lyudi')
        люд += len(л) if isinstance(л, list) else int(з.get('людей') or 0)
    возр = int(time.time() - os.path.getmtime(п))
    жив = 'ЖИВ' if возр < 180 else ('молчит %d мин' % (возр // 60))
    print(f'   {имя:34} записей {n:5} людей {люд:5} ошибок {осш:4} | {жив}')
