# -*- coding: utf-8 -*-
"""Вердикты провайдера — в словарь ОТДЕЛЬНЫМИ колонками, а не поверх моих.

Разбор 300 серий с неустановленным принципом дал:

    РАЗОБРАНО: принцип назван   77   (центробежный 31, винтовой 30, поршневой 13, мембранный 3)
    непонятно                   64
    НЕ наша машина             159

«Больше половины — не наша машина» это крупное число, и я посмотрела глазами десять строк,
прежде чем ему верить. Оказалось не то, что я думала: это не чужие машины, это **позиционные
номера**, которые мой сборщик серий принял за серии —

    К-3/2, К057, К04, К2, АК001-007, К-7/2   «позиция с номером, серия не указана»
    ТГ-10                                    «ТГ — турбогенератор, признаков компрессора нет»
    WP 400 J.P.                              «WP обычно водяной насос»

То есть провайдер видит ровно тот класс, который мой заслон не ловил: заслон отсекает хвосты
«поз.», «зав. №», «инв. №», а голое «К-3/2» для него неотличимо от серии «К-250-61-5».
Проверочные строки в другую сторону выглядят верно: GA7 7,5FF — винтовой Atlas Copco,
ТВ-2152 — турбовоздуходувка (центробежная), ГПА-25/76 — центробежный, Peak NM32LA —
мембранный генератор азота.

ЧТО ДЕЛАЮ. Дописываю в словарь три колонки: `princip_provajder`, `mashina_provajder`,
`pochemu_provajder`. СВОИ колонки не трогаю — разделять, а не подменять: пусть в строке будет
видно и то, что решил мой прибор, и то, что сказал провайдер, и по какому признаку.

ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ прогона был чист: выдуманному «ЩВАРЦКОПФЕРЪ-5» во всех восьми пачках
дан «непонятно» и «не наша машина».

Числа в КОНЦЕ.
"""
import collections
import csv
import io
import json
import os
import re
import urllib.request

SCRATCH = os.environ.get('P25_SCRATCH', '.')
SLOVAR = os.path.join(SCRATCH, 'PARK-SLOVAR-EDINYY.csv')
VERDIKTY = os.path.join(SCRATCH, 'PARK-SERII-PRINCIP-PROVAJDER-3S.jsonl')
POZICIYA = re.compile(r'^(АК|К|Ц|ВК|ТВ)[- ]?\d{1,3}([/\-]\d{1,3})?$', re.I)
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

verd = {}
for s in io.open(VERDIKTY, encoding='utf-8'):
    try:
        z = json.loads(s)
    except Exception:  # noqa: BLE001
        continue
    verd[z.get('oboznachenie')] = z

stroki, kol = [], None
with io.open(SLOVAR, encoding='utf-8-sig') as f:
    r = csv.DictReader(f, delimiter=';')
    kol = list(r.fieldnames)
    for row in r:
        stroki.append(row)
for k in ('princip_provajder', 'mashina_provajder', 'pochemu_provajder'):
    if k not in kol:
        kol.append(k)

sch = collections.Counter()
pohozhe_na_poziciyu = []
for row in stroki:
    ob = (row.get('oboznachenie') or '').strip()
    z = verd.get(ob)
    if not z:
        continue
    row['princip_provajder'] = z.get('princip') or ''
    row['mashina_provajder'] = 'наша' if z.get('nasha_mashina') else 'НЕ наша'
    row['pochemu_provajder'] = (z.get('pochemu') or '')[:180]
    sch['строк словаря, которым дописан вердикт'] += 1
    if not z.get('nasha_mashina'):
        sch['вердикт «НЕ наша машина»'] += 1
        if POZICIYA.match(ob):
            sch['   из них похоже на ПОЗИЦИОННЫЙ номер'] += 1
            pohozhe_na_poziciyu.append(ob)
    elif z.get('princip') == 'непонятно':
        sch['вердикт «непонятно»'] += 1
    else:
        sch['вердикт: принцип назван'] += 1
        # расхождение с моим принципом называется, а не сглаживается
        moy = (row.get('princip') or '').strip()
        if moy and moy not in ('не установлен', z.get('princip')):
            sch['РАСХОЖДЕНИЕ: мой принцип «%s», его «%s»' % (moy, z.get('princip'))] += 1

with io.open(SLOVAR, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=kol, delimiter=';', extrasaction='ignore')
    w.writeheader()
    w.writerows(stroki)
try:
    rq = urllib.request.Request('%s/%s' % (drop, os.path.basename(SLOVAR)),
                                data=io.open(SLOVAR, 'rb').read(), method='PUT', headers=tok)
    vyl = op.open(rq, timeout=300).read().decode('utf-8', 'replace')[:70]
except Exception as e:  # noqa: BLE001
    vyl = 'НЕ ВЫЛОЖЕН: %s' % str(e)[:50]

print('\n\n########## ЧИСЛА')
print('  строк в словаре                                   %5d' % len(stroki))
print('  вердиктов провайдера прочитано                    %5d' % len(verd))
for k, v in sch.most_common():
    print('  %-52s %5d' % (k[:52], v))
print('  примеры позиционных: %s' % ', '.join(pohozhe_na_poziciyu[:10]))
print('  выложен: %s' % vyl)
print('ИТОГ ' + json.dumps({'дописано': sch['строк словаря, которым дописан вердикт'],
                            'не наша машина': sch['вердикт «НЕ наша машина»'],
                            'похоже на позицию': sch['   из них похоже на ПОЗИЦИОННЫЙ номер']},
                           ensure_ascii=False))
