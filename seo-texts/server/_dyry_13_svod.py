# -*- coding: utf-8 -*-
"""Добивка: чужие домены у пустых паспортов (дыра 2), адресные примеры дыры 4,
и сборка общего файла C:\\sender\\_tmp\\diagnoz-dyry.json. Только чтение."""
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')
os.environ['NO_BROWSER'] = '1'
RO = 'file:C:/sender/enrich.db?mode=ro'

import enrich_contacts as EC  # noqa: E402
import zenno_most as ZM  # noqa: E402

c = sqlite3.connect(RO, uri=True, timeout=60)
mnogo = {r[0]: r[1] for r in c.execute('select domen, kompaniy from domeny_mnogo_kompaniy')}
negodnye = {r[0]: r[1] for r in c.execute("select domen, coalesce(uroven,'') from domeny_negodnye")}
# домены, которые встречаются у >1 компании в самой базе
dom_kol = {}
for (s,) in c.execute("select coalesce(site,'') from companies where coalesce(site,'')<>''"):
    m = re.match(r'https?://([^/]+)', s if s.startswith('http') else 'http://' + s)
    d = (m.group(1) if m else s).lower()
    d = d[4:] if d.startswith('www.') else d.split('/')[0]
    dom_kol[d] = dom_kol.get(d, 0) + 1
aliexp = [(str(r[0]), r[1], r[2]) for r in c.execute(
    "select inn, coalesce(name,''), coalesce(site,'') from companies "
    "where site like '%aliexpress%' or site like '%gorzdrav%' or site like '%domclick%' "
    "or cand_site like '%aliexpress%' or cand_site like '%gorzdrav%' "
    "or cand_site like '%domclick%'")]
c.close()
print('компаний на aliexpress/gorzdrav/domclick:', len(aliexp))
for a in aliexp[:8]:
    print('  ', a[0], a[2][:40], a[1][:40])

# ---------- дыра 2: чей это домен ----------
d2 = json.load(open(r'C:\sender\_tmp\dyra2.json', encoding='utf-8'))
celi2 = d2['celi']


def dm(u):
    m = re.match(r'https?://([^/]+)', u if str(u).startswith('http') else 'http://' + str(u))
    d = (m.group(1) if m else str(u)).lower()
    return d[4:] if d.startswith('www.') else d.split('/')[0]


metki = {}
top = {}
for p in celi2:
    u = p.get('kesh_site') or p.get('komp_site') or ''
    d = dm(u)
    if not d:
        continue
    top[d] = top.get(d, 0) + 1
    if ZM._ploshchadka(u):
        k = 'мерка площадок (справочник/витрина)'
    elif not EC._is_own_site('http://' + d):
        k = 'мерка _is_own_site: агрегатор/платформа'
    elif d in negodnye:
        k = 'домен в domeny_negodnye'
    elif mnogo.get(d, 0) >= 2 or dom_kol.get(d, 0) >= 2:
        k = 'домен закреплён за >=2 компаниями базы'
    else:
        k = 'домен выглядит собственным'
    p['domen_verdikt'] = k
    metki[k] = metki.get(k, 0) + 1
print('ПУСТЫЕ ПАСПОРТА (%d) — чей домен:' % len(celi2),
      json.dumps(dict(sorted(metki.items(), key=lambda x: -x[1])), ensure_ascii=False))
print('топ доменов пустых паспортов:', json.dumps(
    dict(sorted(top.items(), key=lambda x: -x[1])[:18]), ensure_ascii=False)[:900])
# пересечение классов
kross = {}
for p in celi2:
    kross.setdefault(p.get('klass', '?'), {})
    v = p.get('domen_verdikt', '?')
    kross[p['klass']][v] = kross[p['klass']].get(v, 0) + 1
print('класс x домен:', json.dumps(kross, ensure_ascii=False)[:1500])

# ---------- дыра 4: адресные примеры ----------
d4 = json.load(open(r'C:\sender\_tmp\dyra4.json', encoding='utf-8'))
dejstvennye = [r for r in d4['podrobno']
               if not r['prichina'].startswith('уже стоит в очереди')]
print('ДЫРА 4, действенных (не «ждут в очереди»):', len(dejstvennye))
print('30 ПРИМЕРОВ:')
for r in dejstvennye[:30]:
    print(' ', r['inn'], '|', r['prichina'][:38], '|', (r['site'] or r['cand'])[:36],
          '|', r['name'][:24])

# ---------- общий файл ----------
d1 = json.load(open(r'C:\sender\_tmp\dyra1_itog.json', encoding='utf-8'))
d3 = json.load(open(r'C:\sender\_tmp\dyra3.json', encoding='utf-8'))
svod = {
 'когда': __import__('time').strftime('%Y-%m-%dT%H:%M:%S'),
 'что_это': 'диагноз четырёх дыр обогащения; числа получены прогонами на сервере, '
            'база enrich.db читалась в режиме ro, ничего не писалось',
 'обстановка': {'companies': 166620, 'из них приехали обзвоном': 113269,
                'файлов кэша': 51551, 'строк site_facts': 23460,
                'цикл fakty_cikl.py': 'жив, PID виден в списке процессов'},
 'dyra1_pasporta': {
   'кэш_без_паспорта': d1['bez_pasporta'],
   'по_условиям_iz_kesha': d1['po_usloviyam'],
   'по_условиям_9_stranic': d1['po_usloviyam_9str'],
   'сверка_с_настоящей_функцией': 'вердикт совпал у всех %d, расхождений %d'
                                  % (d1['bez_pasporta'], len(d1['sverka_razoshlos'])),
   'заблокированы_навсегда': len(d1['zablokirovany']),
   'заблокированы_навсегда_9стр': len(d1['zablokirovany_9str']),
   'примеры30': d1['primery30'],
   'список_заблокированных': d1['zablokirovany']},
 'dyra2_pustye_pasporta': {
   'распределение_карточек': d2['raspr'],
   'без_единого_фактического_поля': len(celi2),
   'классы': d2['klassy'], 'по_note': d2['po_note'],
   'чей_домен': metki, 'топ_доменов': dict(sorted(top.items(), key=lambda x: -x[1])[:40]),
   'примеры30': [{k: p.get(k) for k in ('inn', 'name', 'kesh_site', 'komp_site',
                                        'stranic', 'stranic_v_razbore', 'znakov_v_razbore',
                                        'dolya_kirillicy', 'klass', 'domen_verdikt',
                                        'fmt', 'per', 'ts')}
                 for p in sorted(celi2, key=lambda x: -(x.get('znakov_v_razbore') or 0))[:30]],
   'полный_список': [p['inn'] for p in celi2]},
 'dyra3_kontakty': {
   'кэш_есть_контактов_нет': d3['vsego_celey'], 'из_них_с_сайтом': d3['s_sajtom'],
   'по_стадиям': d3['stadii'], 'выборка': d3['vyborka'],
   'полный_список': d3['celi']},
 'dyra4_ne_obhodili': {
   'всего': d4['vsego'], 'старая_часть_базы': d4['staryh'], 'причины': d4['prichiny'],
   'живость_выборки': d4['zhiv'],
   'действенных': len(dejstvennye), 'примеры30': dejstvennye[:30],
   'полный_список_действенных': [r['inn'] for r in dejstvennye]},
 'адресные_проверки': {'aliexpress_gorzdrav_domclick': aliexp[:40]},
}
p = r'C:\sender\_tmp\diagnoz-dyry.json'
with open(p, 'w', encoding='utf-8') as f:
    json.dump(svod, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
print('ЗАПИСАН', p, os.path.getsize(p), 'байт')
