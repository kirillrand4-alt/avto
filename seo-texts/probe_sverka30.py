# -*- coding: utf-8 -*-
"""Итог сверки 30 имён 1-й сессии: клиент отвалился по времени, читаю поток на сервере."""
import collections
import json
import os

put = r'C:\seostat\drop\3s-sverka-30-imen.jsonl'
if not os.path.exists(put):
    print('потока нет — задание ещё не дошло до записи')
    raise SystemExit
n = tel = poch = 0
sboev = collections.Counter()
primery = []
for ln in open(put, encoding='utf-8'):
    if not ln.strip():
        continue
    z = json.loads(ln)
    n += 1
    if z.get('err'):
        sboev[str(z['err'])[:60]] += 1
        continue
    k = z.get('kontakty') or []
    t = [x for x in k if x['tip'] == 'телефон']
    if t:
        tel += 1
        if len(primery) < 4:
            primery.append({'fio': z.get('fio'), 'nomer': t[0]['znachenie'],
                            'uverennost': t[0].get('uverennost'),
                            'pochemu': (t[0].get('pochemu') or '')[:90]})
    if any(x['tip'] == 'почта' for x in k):
        poch += 1
print(json.dumps({'пройдено': n, 'с_телефоном': tel, 'с_почтой': poch,
                  'сбоев': dict(sboev), 'примеры': primery}, ensure_ascii=False, indent=1))
