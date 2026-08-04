# -*- coding: utf-8 -*-
"""Сколько компаний площадки уже сшито с ИНН и скольких надо дорешить. Размер работы.

ЧТО УСТАНОВЛЕНО ОПЫТОМ, А НЕ ПРЕДПОЛОЖЕНО:

  * `cid` из выгрузки НЕ равен `company_id` строк выдачи — не совпал ни у одного из
    трёх проверенных предприятий;
  * НАЗВАНИЕ в выдаче торговое, а не юридическое: company_id 7571 подписан
    «Балаковские Минудобрения», а ИНН на его странице — 5103070023, то есть АО
    «АПАТИТ», наш покупатель. Искать по названию нельзя в обе стороны;
  * ИНН напечатан на странице компании и сходится. Он единственный, кто не лжёт.

ОТСЮДА РАЗВОРОТ НАПРАВЛЕНИЯ. Идти надо не «от наших 491 к площадке» (не по чему
искать), а «от компаний площадки к нашим»: у каждой компании, встреченной в списке
закупок, узнать ИНН и пересечь с нашими. Это тот же урок, что дала 1-я сессия про
карточки и что я сама записала про реестр ЭПБ: канал широкий, а список целей узкий,
и широта пропадает зря.

Прибор считает размер работы: сколько разных компаний встречено в уже скачанном
списке, у скольких ИНН уже известен из лежащих рядом файлов, скольких надо спросить.
"""
import collections
import csv
import json
import os
import sqlite3

csv.field_size_limit(10 ** 8)
D = r'C:\seostat\drop\drop-storage'
SPISKI = (os.path.join(D, 'tp-spisok.csv'), os.path.join(D, 'tp-kartochki-polnye.csv'))
SLOVARI = (os.path.join(D, 'tp-zakupki-po-vladelcam.csv'),
           os.path.join(D, 'tp-cid-inn.csv'), os.path.join(D, 'tp-inn.csv'))

# Компании, встреченные в скачанном: id -> как подписана.
vstrecheno = {}
for p in SPISKI:
    if not os.path.exists(p):
        continue
    with open(p, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f, delimiter=';'):
            cid = str(r.get('company_id') or '').strip()
            if cid:
                vstrecheno.setdefault(cid, (r.get('company') or '').strip())

# Известные связи company_id -> ИНН, из ЛЮБОГО файла, где обе колонки есть.
izvestno = {}
for p in SLOVARI:
    if not os.path.exists(p):
        continue
    with open(p, encoding='utf-8-sig', newline='') as f:
        rd = csv.DictReader(f, delimiter=';')
        polya = rd.fieldnames or []
        kc = next((x for x in polya if x and x.lower() in ('company_id', 'cid')), '')
        ki = next((x for x in polya if x and x.lower() == 'inn'), '')
        if not (kc and ki):
            continue
        for r in rd:
            c, i = str(r.get(kc) or '').strip(), (r.get(ki) or '').strip()
            if c and i:
                izvestno.setdefault(c, i)

b = sqlite3.connect('file:C:/seostat/data/p25.db?mode=ro', uri=True)
nashi = {i for (i,) in b.execute('select inn from company')}
mesta = {i: m for i, m in b.execute('select inn, coalesce(mesto_po_summe,9999) from company')}

nashi_cid = {c: i for c, i in izvestno.items() if i in nashi}
neizvestnye = [c for c in vstrecheno if c not in izvestno]

# Сколько закупок висит на компаниях с неизвестным ИНН — цена незнания.
zakupok_u_neizvestnyh = collections.Counter()
for p in SPISKI:
    if not os.path.exists(p):
        continue
    with open(p, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f, delimiter=';'):
            cid = str(r.get('company_id') or '').strip()
            if cid and cid not in izvestno:
                zakupok_u_neizvestnyh[cid] += 1

print('самые крупные компании с НЕИЗВЕСТНЫМ ИНН (по числу закупок в скачанном):')
for cid, n in zakupok_u_neizvestnyh.most_common(15):
    print('   company_id %-8s закупок %4d  %s' % (cid, n, vstrecheno.get(cid, '')[:44]))

print('ИТОГ ' + json.dumps({
    'компаний встречено в скачанном': len(vstrecheno),
    'из них ИНН уже известен': len(vstrecheno) - len(neizvestnye),
    'ИНН НАДО СПРОСИТЬ': len(neizvestnye),
    'уже опознано как НАШИ покупатели': len(set(nashi_cid.values())),
    'наших в первой сотне по продажам': len([i for i in set(nashi_cid.values())
                                             if mesta.get(i, 9999) <= 100]),
    'закупок висит на неопознанных': sum(zakupok_u_neizvestnyh.values()),
}, ensure_ascii=False))
