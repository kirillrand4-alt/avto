# -*- coding: utf-8 -*-
"""Сколько ИНН из выгрузки ЕИС ДЕЙСТВИТЕЛЬНО новых. Два прогона дали 272 и 424 — проверяю прибор.

Код между прогонами не менялся, а число новых выросло в полтора раза. Значит менялся не
ответ ЕИС, а мой список «уже известных»: он собирается запросом к `companies`, и если база
в этот момент писалась соседней сессией, чтение могло вернуть меньше строк. Правило смены:
крупное изменение числа — повод проверить прибор, а не радоваться.

Считаю честно и печатаю ВСЕ опоры сразу: сколько ИНН в базе всего, по скольким таблицам,
сколько из 538 найдено в каждой. Если число известных снова окажется маленьким — виновата
не выгрузка.
"""
import io
import json
import os
import sqlite3

VYGRUZKA = r'C:\sender\_ops\PARK-EIS-ZAKAZCHIKI-3S.jsonl'
BAZY = [(r'C:\sender\enrich.db', ['companies', 'requisites', 'signals']),
        (r'C:\seostat\data\centrifugal.db', ['company', 'fact']),
        (r'C:\seostat\drop\drop-storage\atlas_copco.db', ['predpriyatiya', 'tenders'])]

nashi = []
for s in io.open(VYGRUZKA, encoding='utf-8'):
    o = json.loads(s)
    if o.get('inn'):
        nashi.append(o['inn'])
nashi_mn = set(nashi)

svod = []
vse_izvestnye = set()
for baza, tabl in BAZY:
    if not os.path.exists(baza):
        svod.append((os.path.basename(baza), '—', 0, 0))
        continue
    cx = sqlite3.connect('file:%s?mode=ro' % baza.replace('\\', '/'), uri=True)
    for t in tabl:
        try:
            kol = [r[1] for r in cx.execute('pragma table_info("%s")' % t)]
        except Exception:  # noqa: BLE001
            continue
        pole = 'inn' if 'inn' in kol else None
        if not pole:
            continue
        est = set()
        for (v,) in cx.execute('select distinct inn from "%s" where inn is not null' % t):
            v = str(v).strip()
            if v.isdigit():
                est.add(v)
        vse_izvestnye |= est
        svod.append((os.path.basename(baza), t, len(est), len(nashi_mn & est)))
    cx.close()

novye = nashi_mn - vse_izvestnye
print('\n\n########## ГДЕ ИСКАЛИ')
for b, t, vsego, nashli in svod:
    print('  %-22s %-16s ИНН в таблице %7d | из наших нашлось %4d' % (b, t, vsego, nashli))
print('\n########## ЧИСЛА')
print('  ИНН в выгрузке ЕИС            %6d  (строк с ИНН %d)' % (len(nashi_mn), len(nashi)))
print('  известных ИНН во всех базах   %6d' % len(vse_izvestnye))
print('  ДЕЙСТВИТЕЛЬНО НОВЫХ           %6d' % len(novye))
print('  --- десять новых')
for i in list(novye)[:10]:
    print('     %s' % i)
print('ИТОГ ' + json.dumps({'в выгрузке': len(nashi_mn), 'известных': len(vse_izvestnye),
                            'новых': len(novye)}, ensure_ascii=False))
