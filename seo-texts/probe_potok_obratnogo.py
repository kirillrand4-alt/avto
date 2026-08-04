# -*- coding: utf-8 -*-
"""Сколько уже собрал серверный обратный ход — читаю поток, а не гадаю по логу клиента."""
import json
import os

put = r'C:\seostat\drop\3s-obratnyy-server.jsonl'
if not os.path.exists(put):
    print('потока нет:', put)
    raise SystemExit
n = tel = poch = vys = 0
for ln in open(put, encoding='utf-8'):
    if not ln.strip():
        continue
    z = json.loads(ln)
    n += 1
    k = z.get('kontakty') or []
    if any(x['tip'] == 'телефон' for x in k):
        tel += 1
    if any(x['tip'] == 'почта' for x in k):
        poch += 1
    vys += sum(1 for x in k if x['tip'] == 'телефон' and x.get('uverennost') == 'высокая')
print(f'серверный обратный ход: пройдено {n}, с телефоном {tel}, с почтой {poch}, '
      f'телефонов высокой уверенности {vys}')
