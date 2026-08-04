# -*- coding: utf-8 -*-
"""Сшить 1 834 ИНН Портала Москвы с базой: что новое, что уже есть, у скольких машина доказана.

ПОЧЕМУ НЕ ЗАВОДИТЬ ВСЕХ ПОДРЯД. Сбор шёл ПО СЛОВАМ («компрессор», «воздуходувка»), значит
центробежность и воздух у этих предприятий НЕ доказаны — ровно та ошибка, что была в файле
30 июля, где колонка «центробежный предмет» стояла у всех 5 681 строки, а текст доказывал у
664. Поэтому здесь каждая строка проходит через ту же разметку, что и факты панели
(musor_faktov), и в отчёт идут три раздельные кучи, а не одно число.

Заводить карточками стоит только тех, у кого предмет закупки САМ доказывает нашу машину.
Остальные остаются в файле с пометкой — по правилу «разделять, а не отсеивать».
"""
import collections
import csv
import importlib.util
import io
import json
import os
import sqlite3
import urllib.request

spec = importlib.util.spec_from_file_location('mf', r'C:\sender\_ops\3s_musor_faktov.py')
mf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mf)

csv.field_size_limit(10 ** 7)
rows = list(csv.DictReader(open(r'C:\seostat\drop\3s-mos-sbor.csv', encoding='utf-8-sig'),
                           delimiter=';'))
cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
est = {r[0] for r in cx.execute('select inn from company')}

po_inn = collections.defaultdict(lambda: {'strok': 0, 'luchshee': '', 'citata': '',
                                          'nazvanie': '', 'summa': 0.0})
RANG = {'наша машина': 3, 'не машина, но признак нашего производства': 2,
        'о машине ничего не сказано': 1, 'текста нет — не мусор, а отсутствие данных': 1}
for r in rows:
    inn = (r.get('zakazchik_inn') or '').strip()
    if not inn:
        continue
    vid, pochemu = mf.razobrat(r.get('predmet') or '')
    z = po_inn[inn]
    z['strok'] += 1
    z['nazvanie'] = z['nazvanie'] or (r.get('zakazchik') or '')[:120]
    try:
        z['summa'] = max(z['summa'], float(r.get('cena') or 0))
    except ValueError:
        pass
    if RANG.get(vid, 0) > RANG.get(z['luchshee'], 0):
        z['luchshee'] = vid
        z['citata'] = (r.get('predmet') or '')[:200]

sch = collections.Counter()
out = []
for inn, z in po_inn.items():
    novyy = inn not in est
    sch[('новый' if novyy else 'уже в базе') + ' | ' + (z['luchshee'] or 'нет разбора')] += 1
    out.append({'inn': inn, 'novyy': '1' if novyy else '', 'nazvanie': z['nazvanie'],
                'strok_zakupok': z['strok'], 'luchshiy_vid': z['luchshee'],
                'maks_summa': z['summa'], 'citata': z['citata']})
out.sort(key=lambda x: (-RANG.get(x['luchshiy_vid'], 0), -x['maks_summa']))
b = io.StringIO()
w = csv.DictWriter(b, fieldnames=list(out[0]), delimiter=';')
w.writeheader()
w.writerows(out)
telo = b.getvalue().encode('utf-8-sig')
req = urllib.request.Request(
    os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
    + '/VAZHNOE-3s-MOSKVA-INN-s-razborom.csv', data=telo, method='PUT',
    headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', ''), 'Content-Type': 'text/csv'})
with urllib.request.urlopen(req, timeout=180) as rr:
    vygr = rr.status
print(json.dumps({'ИНН_всего': len(po_inn), 'по_разбору': dict(sch.most_common()),
                  'выгрузка': vygr,
                  'к_заведению_карточками': sum(1 for x in out if x['novyy']
                                                and x['luchshiy_vid'] == 'наша машина')},
                 ensure_ascii=False, indent=1))
