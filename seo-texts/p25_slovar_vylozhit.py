# -*- coding: utf-8 -*-
"""СЛОВАРЬ СЕРИЙ: собрать и ВЫЛОЖИТЬ на дроп файлом. Это рабочий артефакт, а не отчёт.

Тот же разбор, что во втором заходе (две оси + три заслона), но с двумя добавками:

  * каждая серия несёт ССЫЛКУ на документ, где она встречена — правило владельца
    «каждый факт доказывается ссылкой, ведущей на доказательство»;
  * серии, у которых вид машины НЕ УСТАНОВЛЕН ни разу, идут в ОТДЕЛЬНЫЙ файл
    «требует проверки», а не выбрасываются и не смешиваются с доказанными.
    Разделять, а не отсеивать.

Файл кладётся на дроп прямо отсюда: DROP_URL и DROP_TOKEN есть в окружении раннера.
"""
import collections
import io
import json
import os
import re
import sqlite3
import urllib.request

ISTOCHNIKI = [(r'C:\seostat\data\centrifugal.db', 'fact'),
              (r'C:\seostat\drop\drop-storage\atlas_copco.db', 'tenders'),
              (r'C:\seostat\drop\drop-storage\atlas_copco.db', 'fakty')]
SERIYA = re.compile(
    r'\b((?:ТВ|ЦК|ЦНД|К|КТК|ВЦ|ЗИФ|НВЭ|ВП|ВМ|ПКС|ЭК|АК|ТГ|ГПА|АДГ|ВК|КР|УКС|ВШ|ТКА|Ц)'
    r'[- ]?\d{1,4}(?:[-/][\dА-Яа-яA-Za-z,\.]{1,8}){0,3})\b', re.U)
PRINCIP = (('центробежный', re.compile(r'центробежн|турбо', re.I)),
           ('винтовой', re.compile(r'винтов', re.I)),
           ('поршневой', re.compile(r'поршнев', re.I)))
VID = (('воздуходувка', re.compile(r'воздуходув|газодув', re.I)),
       ('нагнетатель', re.compile(r'нагнетател', re.I)),
       ('ВРУ', re.compile(r'воздухоразделен|\bВРУ\b|криоген', re.I)),
       ('генератор азота/кислорода', re.compile(r'генератор\w*\s+(?:азота|кислорода)|'
                                                r'азотн\w+\s+станци|кислородн\w+\s+станци', re.I)),
       ('МКС', re.compile(r'\bМКС\b|передвижн\w+\s+компрессор|мобильн\w+\s+компрессор', re.I)),
       ('осушитель', re.compile(r'осушител', re.I)),
       ('ГПА', re.compile(r'газоперекачивающ|\bГПА\b', re.I)),
       ('компрессор', re.compile(r'компрессор', re.I)))
CHUZH = re.compile(r'вентилятор|дымосос|\bнасос\w*\b|градирн|конвейер|кондиционер|трактор|'
                   r'сельхоз|автотранспорт|стартер|John Deere|New Holland|MacDon', re.I)
POMESH = re.compile(r'здани|укрыти|помещени|цех\b|корпус', re.I)
POZ = re.compile(r'поз\.?\s*$|позици\w*\s*$|№\s*$', re.I)
URL = re.compile(r'https?://\S+')

s_ = collections.defaultdict(lambda: {'v': 0, 'p': collections.Counter(),
                                      'vid': collections.Counter(), 'inn': set(),
                                      'cit': '', 'url': set(), 'srez': collections.Counter()})
for baza, tabl in ISTOCHNIKI:
    if not os.path.exists(baza):
        continue
    cx = sqlite3.connect('file:%s?mode=ro' % baza.replace('\\', '/'), uri=True)
    kol = [r[1] for r in cx.execute('pragma table_info("%s")' % tabl)]
    if not kol:
        cx.close(); continue
    pinn = 'inn' if 'inn' in kol else None
    for r in cx.execute('select %s from "%s"' % (','.join('"%s"' % k for k in kol), tabl)):
        d = dict(zip(kol, r))
        tekst = ' '.join(str(v) for v in r if v is not None)
        if len(tekst) < 8:
            continue
        for m in SERIYA.finditer(tekst):
            s = re.sub(r'\s+', '', m.group(1)).upper()
            do = tekst[max(0, m.start() - 60):m.start()]
            okno = tekst[max(0, m.start() - 120):m.end() + 120]
            z = s_[s]
            if POZ.search(do):
                z['srez']['позиция'] += 1; continue
            if CHUZH.search(okno):
                z['srez']['чужая машина'] += 1; continue
            if POMESH.search(okno) and not re.search(r'компрессор|воздуходув|нагнетател', okno, re.I):
                z['srez']['помещение'] += 1; continue
            z['v'] += 1
            for i, rg in PRINCIP:
                if rg.search(okno):
                    z['p'][i] += 1; break
            for i, rg in VID:
                if rg.search(okno):
                    z['vid'][i] += 1; break
            if pinn and str(d.get(pinn) or '').strip():
                z['inn'].add(str(d[pinn]).strip())
            for u in URL.findall(tekst)[:2]:
                z['url'].add(u)
            if not z['cit']:
                z['cit'] = re.sub(r'[\s;]+', ' ', okno)[:180]
    cx.close()

dok, proverit = [], []
for s, z in s_.items():
    if z['v'] < 2:
        continue
    pr = (z['p'].most_common(1) or [('не установлен', 0)])[0][0]
    vd = (z['vid'].most_common(1) or [('не установлен', 0)])[0][0]
    row = [s, pr, vd, z['v'], len(z['inn']), len(z['url']),
           ' | '.join(list(z['url'])[:3]), z['cit'].replace(';', ',')]
    (dok if vd != 'не установлен' else proverit).append(row)

SHAPKA = 'seriya;princip;vid;vstrech;innov;ssylok;ssylki;citata\n'


def sohranit(imya, rows):
    p = os.path.join(r'C:\sender\_ops', imya)
    with io.open(p, 'w', encoding='utf-8-sig') as f:
        f.write(SHAPKA)
        for r in sorted(rows, key=lambda x: -x[3]):
            f.write(';'.join(str(x) for x in r) + '\n')
    return p


def na_drop(put):
    drop = os.environ.get('DROP_URL', '').rstrip('/')
    tok = os.environ.get('DROP_TOKEN', '')
    if not (drop and tok):
        return 'нет DROP_URL/DROP_TOKEN'
    telo = io.open(put, 'rb').read()
    imya = os.path.basename(put)
    gran = '----park3s'
    body = (('--%s\r\nContent-Disposition: form-data; name="file"; filename="%s"\r\n'
             'Content-Type: application/octet-stream\r\n\r\n' % (gran, imya)).encode()
            + telo + ('\r\n--%s--\r\n' % gran).encode())
    req = urllib.request.Request(drop + '/up', data=body, method='POST', headers={
        'X-Drop-Token': tok,
        'Content-Type': 'multipart/form-data; boundary=%s' % gran})
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        return op.open(req, timeout=120).read().decode('utf-8', 'replace')[:200]
    except Exception as e:  # noqa: BLE001
        return 'не вышло: %s' % str(e)[:160]


p1 = sohranit('PARK-SLOVAR-SERII-3S.csv', dok)
p2 = sohranit('PARK-SLOVAR-SERII-PROVERIT-3S.csv', proverit)
o1 = na_drop(p1)
o2 = na_drop(p2)

print('\n\n########## ЧИСЛА')
print('  серий ДОКАЗАННЫХ (вид машины назван)   %5d' % len(dok))
print('  серий ТРЕБУЮТ ПРОВЕРКИ (вид не назван) %5d' % len(proverit))
print('  из доказанных со ссылкой на документ   %5d'
      % sum(1 for r in dok if r[5] > 0))
print('  из доказанных БЕЗ ссылки               %5d'
      % sum(1 for r in dok if r[5] == 0))
print('  разных ИНН по доказанным сериям        %5d'
      % len({i for s, z in s_.items() for i in z['inn'] if z['v'] >= 2}))
print('\n  выложено: %s -> %s' % (os.path.basename(p1), o1))
print('  выложено: %s -> %s' % (os.path.basename(p2), o2))
print('ИТОГ ' + json.dumps({'доказанных': len(dok), 'на проверку': len(proverit)},
                           ensure_ascii=False))
