# -*- coding: utf-8 -*-
"""Где именной канал перестаёт платить: отдача по местам списка, а не в среднем.

ЗАЧЕМ. Кусок мест 111-150 дал 16 подтверждённых страницей из 147 человек. Следующий, места
151-200, дал **1 из 156** при том же числе запросов (250) и том же заслоне. Средняя цифра по
каналу — 3,5 % — такое различие прячет: она складывает первую полусотню мест с последней и
показывает число, которого нет ни у одного отрезка.

ГИПОТЕЗА, КОТОРУЮ НАДО ПРОВЕРИТЬ, А НЕ ПРИНЯТЬ. Места нумерованы по сумме покупок: чем ниже
место, тем меньше предприятие. У малого предприятия и сайт беднее, и карточек закупок в
индексе меньше — значит падает не выдача, а ПОДТВЕРЖДАЕМОСТЬ. Если это так, то дальше по
списку надо не гнать тот же канал, а менять способ подтверждения; если не так — искать
поломку в самом канале.

Считается по отрезкам мест: сколько запросов, людей, подтверждённых, и сколько предприятий
отрезка вообще отдали хоть одного человека. Место берётся из `company.mesto_po_summe`.
"""
import collections
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\_ops')
import _3s_chuzhaya_stranica as CH  # noqa: E402

POTOK = r'C:\sender\_ops\p25-imena.jsonl'
BAZA = 'file:C:/seostat/data/p25.db?mode=ro'
OTREZKI = ((1, 20), (21, 50), (51, 80), (81, 110), (111, 150), (151, 200), (201, 999))


def sayty():
    d = {}
    for put in (r'C:\sender\_ops\3s_p25_sayty_2s.csv',
                r'C:\sender\_ops\3s_p25_sayty.csv'):
        if not os.path.exists(put):
            continue
        import csv
        for r in csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';'):
            v = r.get('ves')
            if v and v.isdigit() and int(v) < 2:
                continue
            if r.get('inn') and r.get('sayt'):
                d.setdefault(r['inn'], r['sayt'])
    return d


def main():
    b = sqlite3.connect(BAZA, uri=True)
    mesto = {i: m for i, m in b.execute(
        'select inn, coalesce(mesto_po_summe, 9999) from company')}
    imena = {i: n for i, n in b.execute(
        'select inn, coalesce(predpriyatie,"") from company')}
    st = sayty()
    po_otrezku = collections.defaultdict(collections.Counter)
    predpr = collections.defaultdict(set)
    predpr_s_lyudmi = collections.defaultdict(set)
    predpr_s_podtv = collections.defaultdict(set)

    def otrezok(m):
        for a, c in OTREZKI:
            if a <= m <= c:
                return '%d-%d' % (a, c)
        return 'вне списка'

    for ln in open(POTOK, encoding='utf-8'):
        try:
            z = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        o = otrezok(mesto.get(z.get('inn'), 9999))
        po_otrezku[o]['запросов'] += 1
        predpr[o].add(z.get('inn'))
        if z.get('err'):
            po_otrezku[o]['сбоев'] += 1
            continue
        for l in z.get('lyudi') or []:
            if l.get('krug') == 'ИСТОЧНИК ЗАПРЕЩЁН':
                po_otrezku[o]['запрещённый источник'] += 1
                continue
            po_otrezku[o]['людей'] += 1
            predpr_s_lyudmi[o].add(z.get('inn'))
            est, _ = CH.stranica_podtverzhdaet(
                l.get('ssylka', ''), st.get(z.get('inn'), ''),
                z.get('predpriyatie', '') or imena.get(z.get('inn'), ''), '', strogo=True)
            if est:
                po_otrezku[o]['ПОДТВЕРЖДЕНО'] += 1
                predpr_s_podtv[o].add(z.get('inn'))

    stroki = []
    for a, c in OTREZKI:
        o = '%d-%d' % (a, c)
        s = po_otrezku.get(o)
        if not s:
            continue
        lyudi = s['людей'] or 0
        podtv = s['ПОДТВЕРЖДЕНО'] or 0
        stroki.append({
            'места': o, 'предприятий': len(predpr[o]), 'запросов': s['запросов'],
            'людей': lyudi, 'подтверждено': podtv,
            'доля_подтверждённых_%': round(100.0 * podtv / lyudi, 1) if lyudi else 0.0,
            'запросов_на_подтверждённого': round(s['запросов'] / podtv, 1) if podtv else None,
            'предприятий_с_людьми': len(predpr_s_lyudmi[o]),
            'предприятий_с_подтверждённым': len(predpr_s_podtv[o]),
            'сайт_известен_у': sum(1 for i in predpr[o] if i in st),
            'запрещённых': s['запрещённый источник'] or 0, 'сбоев': s['сбоев'] or 0,
        })
    for z in stroki:
        print('REC ' + json.dumps(z, ensure_ascii=False))
    print('ИТОГ ' + json.dumps({'отрезков': len(stroki), 'сайтов известно всего': len(st)},
                               ensure_ascii=False))


if __name__ == '__main__':
    main()
