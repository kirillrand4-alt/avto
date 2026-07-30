# -*- coding: utf-8 -*-
"""Клиенты наших целей ПО 223-ФЗ отдельно от 44-ФЗ.

Прежний замер дал «35 заказчиков, промышленных ноль» и я закрыл идею. Линза
показала, что вывод шире доказанного: по 44-ФЗ заказчик это бюджетное
учреждение ПО ОПРЕДЕЛЕНИЮ ЗАКОНА, то есть «все бюджетные» там не свойство
мира, а свойство метода. По 223-ФЗ заказчики другие: госкорпорации, их дочки,
естественные монополии, компании с госучастием — у них есть производство.

Разделяем по адресу карточки: у 223-ФЗ в ссылке есть contractfz223 или /223/.
"""
import io
import json
import os
import re
import sys
import time
sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC
import enrich_db as EDB

БЮДЖЕТ = float(sys.argv[1]) if len(sys.argv) > 1 else 400.0
ЛИМИТ = int(sys.argv[2]) if len(sys.argv) > 2 else 45
НАЧАЛО = time.time()
ПОТОК = r'C:\seostat\drop\clients_223.jsonl'
db = EDB.EnrichDB()
e = db.cx

_ХВОСТ = re.compile(r'\s+(?:Контракт\s*№|Договор\s*№|Объекты\s+закупки|'
                    r'Номер\s+извещения)\b.*$', re.I | re.S)
_БЮДЖ = re.compile(r'школ|детск|больниц|поликлин|санатор|учрежден|'
                   r'администрац|управлени|департамент|комитет|музе|'
                   r'библиотек|интернат|пристав|казённ|казен', re.I)
_ПРОМ = re.compile(r'завод|комбинат|производств|фабрик|цемент|металл|'
                   r'химическ|нефт|газ|энерг|водоканал|теплос|горн|'
                   r'машиностро|рудник|шахт|порт|аэропорт|железн|сет[ий]\b', re.I)


def норм(s):
    s = re.sub(r'["«»\']', '', (s or '').lower())
    s = re.sub(r'\b(ооо|оао|зао|ао|пао|нао|гуп|муп|фгуп|фгбу|гбу|мбу|'
               r'общество|акционерное|публичное|непубличное|с ограниченной '
               r'ответственностью|государственное|муниципальное|унитарное|'
               r'предприятие|федеральное|бюджетное|филиал)\b', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


наши = set()
for r in e.execute('SELECT name FROM companies WHERE name IS NOT NULL'):
    к = норм(r[0])
    if len(к) >= 4:
        наши.add(к)

видано = set()
if os.path.exists(ПОТОК):
    for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            видано.add(str(json.loads(ln).get('inn')))
        except Exception:  # noqa: BLE001
            pass
цели = [r[0] for r in e.execute(
    'SELECT inn FROM companies ORDER BY COALESCE(revenue_rub,0) DESC LIMIT 700')
    if str(r[0]) not in видано][:ЛИМИТ]

out = {'пройдено': 0, 'карточек_44': 0, 'карточек_223': 0,
       'заказчиков_44': 0, 'заказчиков_223': 0}
зак44, зак223 = {}, {}
print(json.dumps({'старт': True, 'целей': len(цели)}, ensure_ascii=False))
ф = io.open(ПОТОК, 'a', encoding='utf-8')
for inn in цели:
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        break
    try:
        r = EC.find_zakupki_supplier(inn, max_cards=8) or {}
    except Exception:  # noqa: BLE001
        continue
    out['пройдено'] += 1
    свои = {'44': [], '223': []}
    for c in (r.get('cards') or []):
        u = c.get('url') or ''
        закон = '223' if ('contractfz223' in u or '/223/' in u) else '44'
        out['карточек_' + закон] += 1
        for имя in (c.get('customers') or r.get('customers') or []):
            ч = _ХВОСТ.sub('', (имя or '').strip()).strip(' ."«»')
            if len(ч) > 8:
                свои[закон].append(ч)
    for имя in set(свои['44']):
        зак44[имя] = зак44.get(имя, 0) + 1
    for имя in set(свои['223']):
        зак223[имя] = зак223.get(имя, 0) + 1
    ф.write(json.dumps({'inn': inn, '44': sorted(set(свои['44'])),
                        '223': sorted(set(свои['223']))},
                       ensure_ascii=False) + '\n')
    ф.flush()
    os.fsync(ф.fileno())
ф.close()


def разбор(словарь):
    пром = [k for k in словарь if _ПРОМ.search(k) and not _БЮДЖ.search(k)]
    бюдж = [k for k in словарь if _БЮДЖ.search(k)]
    новые = [k for k in пром if норм(k) not in наши]
    return {'всего': len(словарь), 'промышленных': len(пром),
            'бюджетных': len(бюдж), 'промышленных_новых': len(новые),
            'примеры_пром': sorted(пром)[:10]}


out['заказчиков_44'] = len(зак44)
out['заказчиков_223'] = len(зак223)
print(json.dumps({'по_44': разбор(зак44)}, ensure_ascii=False)[:900])
print(json.dumps({'по_223': разбор(зак223)}, ensure_ascii=False)[:1200])
print(json.dumps(out, ensure_ascii=False))
