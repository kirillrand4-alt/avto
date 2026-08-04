# -*- coding: utf-8 -*-
"""Сколько ещё карточек площадки МОЖНО забрать по нашим 491 — то есть какова цена приза.

Разбор текста карточек дал первые три предприятия, закрытые по букве ТЗ (технарь +
личный мобильный + первоисточник), и это при 314 карточках всего на 47 предприятий,
из которых наших только 10. То есть узкое место не в разборе, а в ЧИСЛЕ КАРТОЧЕК.

Прибор отвечает на один вопрос: у скольких из 491 нашего покупателя есть опознанная
карточка компании на площадке (`cid`), но карточки закупок ещё не выкачаны. Это и
есть размер невыбранного, и по нему решается, стоит ли просить у соседа догрузку.
"""
import collections
import json
import os
import sqlite3

ISHODNIK = (r'C:\sender\_ops\tp_raw.json',)


def s_dropa(imya):
    import urllib.request
    url, tok = os.environ.get('DROP_URL', ''), os.environ.get('DROP_TOKEN', '')
    rq = urllib.request.Request(url.rstrip('/') + '/' + imya)
    rq.add_header('X-Drop-Token', tok)
    return json.loads(urllib.request.urlopen(rq, timeout=300).read().decode('utf-8'))


put = next((p for p in ISHODNIK if os.path.exists(p)), '')
d = json.load(open(put, encoding='utf-8')) if put else s_dropa('tp_raw.json')
komp, kart = d.get('компании') or {}, d.get('карточки') or []

b = sqlite3.connect('file:C:/seostat/data/p25.db?mode=ro', uri=True)
nashi = {i for (i,) in b.execute('select inn from company')}
# Место по сумме покупок: приз считается не в штуках, а в деньгах.
mesta = {i: m for i, m in b.execute('select inn, coalesce(mesto_po_summe, 9999) from company')}

s_kartochkami = {k['inn'] for k in kart}
sch = collections.Counter()
gotovy = []
for inn in nashi:
    z = komp.get(inn) or {}
    est_cid = bool(z.get('cid'))
    est_kart = inn in s_kartochkami
    if est_kart:
        sch['карточки уже выкачаны'] += 1
    elif est_cid:
        sch['ЕСТЬ cid, КАРТОЧЕК НЕТ — вот приз'] += 1
        gotovy.append((mesta.get(inn, 9999), inn, (z.get('tp_name') or '')[:40],
                       z.get('тендеров', ''), z.get('годных', '')))
    elif inn in komp:
        sch['есть в выгрузке, но компания на площадке не опознана'] += 1
    else:
        sch['в выгрузке площадки нет вовсе'] += 1

gotovy.sort()
print('ГОТОВЫ К ДОГРУЗКЕ (по месту в продажах, первые 25):')
for m, inn, nm, t, g in gotovy[:25]:
    print('  место %4s  %s  %-40s тендеров %s, годных %s' % (m, inn, nm, t, g))
print('ИТОГ ' + json.dumps({
    'наших покупателей': len(nashi), 'по видам': dict(sch),
    'в первой сотне по продажам среди готовых': len([x for x in gotovy if x[0] <= 100]),
}, ensure_ascii=False))
