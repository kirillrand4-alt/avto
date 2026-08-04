# -*- coding: utf-8 -*-
"""Проверка предложенной формулы на живой базе: что поднимется, что упадёт, и не сломается ли.

ПОЧЕМУ НЕ ХВАТИТ РАССУЖДЕНИЯ. Формула, которая красиво звучит, может на живых данных
схлопнуть всё в одну кучу или, наоборот, поднять пустышки. Поэтому здесь считаются оба
порядка — старый и предложенный — и печатается: как меняются верхние двадцать, сколько
предприятий попадает в каждую из двух очередей и сколько лидов с личным номером стояли внизу
старого списка.
"""
import collections
import importlib.util
import json
import re
import sqlite3

spec = importlib.util.spec_from_file_location('pp', r'C:\sender\_ops\3s_prioritet_prodazhi.py')
pp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pp)

cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
sale = sqlite3.connect(r'C:\seostat\data\centro_sales.db')
skrytye = {r[0] for r in sale.execute("select inn from hidden_item where kind='company'")}

# Общие номера считаем по всей базе: номер у 2+ РАЗНЫХ предприятий личным не бывает.
obshchie = collections.Counter()
karta = collections.defaultdict(set)
for inn, phone in cx.execute("select coalesce(inn,''), coalesce(phone,'') from person "
                             "where coalesce(phone,'') <> ''"):
    c = re.sub(r'\D', '', phone)
    if len(c) >= 10:
        karta[c[-10:]].add(inn)
obshchie = {k for k, v in karta.items() if len(v) > 1}

itog = []
for inn, sost, vazhn, sreda, tipy, srok in cx.execute(
        "select inn, coalesce(sostoyaniya_po_faktam,''), coalesce(vazhnost_pokupki,0), "
        "coalesce(sreda_po_faktam,''), coalesce(sostoyanie_potverzhdeno_faktom,''), "
        "coalesce(chego_ne_hvataet,'') from company"):
    if inn in skrytye:
        continue
    lich_teh = lich = imen_teh = obshch = 0
    for ph, teh, person in cx.execute(
            "select coalesce(phone,''), coalesce(is_tech,0), coalesce(person,'') "
            "from person where inn = ?", (inn,)):
        c = re.sub(r'\D', '', ph)
        if len(c) >= 10:
            if c[-10:] in obshchie:
                obshch += 1
            elif c[-10:].startswith('9'):
                lich += 1
                lich_teh += 1 if teh else 0
            else:
                obshch += 1
        elif person and teh:
            imen_teh += 1
    dos = pp.stepen_dosyagaemosti(lich_teh, lich, imen_teh, obshch)
    pov = pp.stepen_povoda(sost, None)
    if 'воздух' in (sreda or '').lower():
        soot = 'центробежная и воздух, доказано текстом первоисточника'
    elif 'газ' in (sreda or '').lower():
        soot = 'центробежная, но газ'
    else:
        soot = 'центробежная, среда не названа'
    p = pp.prioritet(pov, soot, dos, 'один источник, есть ссылка на первоисточник')
    itog.append({'inn': inn, 'staryy': float(vazhn), 'novyy': p,
                 'ochered': pp.ochered(dos, soot, pov), 'dos': dos, 'pov': pov, 'soot': soot})

o = {'предприятий_видимых': len(itog),
     'по_очередям': dict(collections.Counter(z['ochered'] for z in itog)),
     'по_досягаемости': dict(collections.Counter(z['dos'] for z in itog))}
star = sorted(itog, key=lambda z: -z['staryy'])[:20]
nov = sorted(itog, key=lambda z: -z['novyy'])[:20]
o['в_старом_топ20_без_номера'] = sum(1 for z in star if z['dos'] == 'ни номера, ни имени')
o['в_новом_топ20_без_номера'] = sum(1 for z in nov if z['dos'] == 'ни номера, ни имени')
o['новый_топ10'] = [[z['inn'], z['novyy'], z['staryy'], z['dos'][:34], z['pov'][:34]]
                    for z in nov[:10]]
# Сколько лидов с личным номером стояли ниже сотого места старого порядка.
poz = {z['inn']: i for i, z in enumerate(sorted(itog, key=lambda z: -z['staryy']))}
o['с_личным_номером_ниже_100_места_в_старом'] = sum(
    1 for z in itog if z['dos'].startswith('личный') and poz[z['inn']] >= 100)
o['всего_с_личным_номером'] = sum(1 for z in itog if z['dos'].startswith('личный'))
print(json.dumps(o, ensure_ascii=False, indent=1))
