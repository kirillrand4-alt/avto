# -*- coding: utf-8 -*-
"""Роли адресов: панель (MEYER-PISALI.csv, «адрес (роль)») против свежей разметки обхода ЦА (ca-kontakty.jsonl).
Только чтение, только счётчики и обезличенные примеры (адрес маскируется)."""
import collections, csv, io, json, re

пан = {}
with io.open(r'C:\seostat\drop\drop-storage\MEYER-PISALI.csv', encoding='utf-8-sig', errors='replace') as f:
    r_ = csv.reader(f, delimiter=';')
    шапка = next(r_)
    ик = next((i for i, h in enumerate(шапка) if 'онтакт' in h), None)
    for row in r_:
        if ик is None or len(row) <= ик:
            continue
        for м in re.finditer(r'([\w.+-]+@[\w-]+(?:\.[\w-]+)+)\s*\(([^)]*)\)', row[ик]):
            пан[м.group(1).lower()] = м.group(2).strip()
наши = {}
for s in io.open(r'C:\sender\server\ca-kontakty.jsonl', encoding='utf-8', errors='replace'):
    try:
        з = json.loads(s)
    except ValueError:
        continue
    if з.get('итог') != 'ok':
        continue
    for x in з.get('номера') or []:
        п = (x.get('почта') or '').lower()
        if п:
            наши[п] = (x.get('роль') or '', x.get('лпр') or '', x.get('чей') or '')
общие = [п for п in пан if п in наши]
пары = collections.Counter((пан[п], наши[п][0]) for п in общие)
по_панели = collections.Counter(пан.values())
print('===ИТОГ===', json.dumps({'адресов_с_ролью_в_панели': len(пан), 'роли_панели': dict(по_панели.most_common(15)),
                                 'есть_в_нашем_обходе': len(общие),
                                 'у_нас_чужой_адрес': sum(1 for п in общие if наши[п][2] == 'другая')}, ensure_ascii=False))
техн = re.compile(r'инженер|механик|энергет|технолог|производ|техдир|ОГМ|ОГЭ', re.I)
тп = [п for п in общие if техн.search(пан[п])]
print('ТЕХ-роли в панели среди общих:', len(тп), dict(collections.Counter(наши[п][0] for п in тп).most_common(8)))
print('ТЕХ-роли в панели всего:', sum(1 for v in пан.values() if техн.search(v)))
print('совпало по смыслу (грубо):', sum(1 for п in общие if пан[п].split()[0][:5].lower() in наши[п][0].lower()))
for (а, б), n in []:
    print(n, '| панель:', а, '| наш разбор:', б)
