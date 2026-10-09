# -*- coding: utf-8 -*-
"""fixG (локально): кандидаты на замену 13 помеченных компаний – следующие лучшие из файла 3 Meyer
по рейтингу ТОГО ЖЕ скрипта отбора Базы 3 (meyer_baza3_v_json.py исполняется как есть, без правок).

Панель – текущий каталог с сервера (копия): все его ИНН считаются «уже в панели» (в т. ч. 13
убираемых – они не могут вернуться кандидатами), а номера 13 убираемых в «номера панели» не идут
(после удаления они не держат группу).

    python3 fixG_kandidaty.py <fajl3.xlsx> <каталог.db> <выход-папка> [сколько=60]
Выход: kandidaty.json (рейтинг, ИНН, название, ОКВЭД, выручка, сайт, связка, номера) и
meyer-fixG-kand.json (формат загрузчика Базы 3 для первых N).
"""
import io
import json
import os
import sqlite3
import sys

VHOD, KAT, OUT = sys.argv[1:4]
SKOLKO = int(sys.argv[4]) if len(sys.argv) > 4 else 60
os.makedirs(OUT, exist_ok=True)
k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
k.row_factory = sqlite3.Row
ubirat = {r[0] for r in k.execute("select inn from company where trim(coalesce(pometka_ocheredi,''))<>''")}
panel = {'kompanii': [{'inn': r['inn'], 'predpriyatie': r['predpriyatie'], 'region': r['region'], 'segment': r['segment'],
                       'vyruchka_rub': r['vyruchka_rub']} for r in k.execute('select * from company')],
         'kontakty': [{'inn': r['inn'], 'value': r['value']} for r in k.execute("select inn, value from contact where kind='phone'")
                      if r['inn'] not in ubirat]}
pp = os.path.join(OUT, 'panel-seychas.json')
io.open(pp, 'w', encoding='utf-8').write(json.dumps(panel, ensure_ascii=False))
skript = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'meyer_baza3_v_json.py')
sys.argv = [skript, VHOD, os.path.join(OUT, 'meyer-fixG-kand.json'), str(SKOLKO), pp]
ns = {'__name__': 'baza3', '__file__': skript}
exec(compile(io.open(skript, encoding='utf-8').read(), skript, 'exec'), ns)
s, cif, svoy, nast, svyaz = ns['s'], ns['cif'], ns['svoy'], ns['nastoyashchiy_mobilnyy'], ns['svyazka_podtverzhdena']
out = []
for n, (reyt, c, ks) in enumerate(ns['kand'], 1):
    out.append({'mesto': n, 'reyting': reyt, 'inn': s(c['ИНН']), 'nazvanie': s(c['Название']), 'region': s(c['Регион']),
                'okved': s(c['Основной ОКВЭД']), 'okvedy_dop': s(c['Доп. ОКВЭД']), 'vyruchka': ns['chislo'](c['Выручка, руб']),
                'god': s(c['Год выручки']), 'sayt': s(c['Сайт']), 'opisanie': s(c['Описание']), 'segment': s(c['Сегмент']),
                'segment_osn': s(c['Сегмент по основному ОКВЭД']), 'svyazka': svyaz(c, ks),
                'nomera': [{'nomer': s(r['Номер']), 'tip': s(r['Тип номера']), 'podpis': s(r['Подпись в базе']),
                            'url': s(r['Ссылка на источник']), 'chya': s(r['Чья страница']), 'istochnik': s(r['Источник']),
                            'fragment': s(r['Как стоит на странице']), 'svoy': svoy(r), 'nastoyashchiy': nast(r)} for r in ks]})
io.open(os.path.join(OUT, 'kandidaty.json'), 'w', encoding='utf-8').write(json.dumps(out, ensure_ascii=False, indent=1))
print('кандидатов вне панели: %d -> %s' % (len(out), os.path.join(OUT, 'kandidaty.json')))
