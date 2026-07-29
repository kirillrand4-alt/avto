# -*- coding: utf-8 -*-
"""Классифицировать клиентов наших целей и добить выборку.

Первый круг дал 22 заказчика, и на глаз это детские сады, школы, санатории и
судебные приставы — то есть бюджетные учреждения, а не заводы с компрессорной.
Так и должно быть: заказчик по 44-ФЗ бюджетное учреждение ПО ОПРЕДЕЛЕНИЮ.
Промышленный заказчик может прийти только из 223-ФЗ, где закупаются
госкорпорации и их дочки. Значит считать надо раздельно.

Попутно чиним дефект разбора: в имя заказчика приклеен хвост карточки
(«... Контракт № 229903 Объекты закупки Транспортные...»). Режем по границе.
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

ПОТОК = r'C:\seostat\drop\clients_of_targets.jsonl'
БЮДЖЕТ = float(sys.argv[1]) if len(sys.argv) > 1 else 240.0
НАЧАЛО = time.time()

_ХВОСТ = re.compile(r'\s+(?:Контракт\s*№|Договор\s*№|Объекты\s+закупки|'
                    r'Номер\s+извещения|Реестровый\s+номер)\b.*$', re.I | re.S)
_БЮДЖЕТ = re.compile(r'администрац|управлени|министерств|департамент|комитет|'
                     r'школ|больниц|поликлин|детск|музе|библиотек|театр|'
                     r'казённ|казен|учрежден|санатор|пристав|суд|полиц|'
                     r'росгвард|военн|интернат|колледж|университет|институт|'
                     r'академи|лице|гимнази|дом культур|соцзащ|пенсион', re.I)
_ПРОМ = re.compile(r'завод|комбинат|производств|фабрик|цемент|металлург|'
                   r'химическ|нефт|газпром|роснефт|энерг|водоканал|теплосет|'
                   r'горно|машиностро|птицефабрик|мясокомбинат|молочн|'
                   r'россет|рждv|железн|порт|аэропорт|рудник|шахт|карьер', re.I)


def чисто(имя):
    return _ХВОСТ.sub('', (имя or '').strip()).strip(' ."«»')


db = EDB.EnrichDB()
e = db.cx


def норм(s):
    s = re.sub(r'["«»\']', '', (s or '').lower())
    s = re.sub(r'\b(ооо|оао|зао|ао|пао|нао|гуп|муп|фгуп|фгбу|гбу|мбу|мбдоу|'
               r'гбоу|мбоу|гку|мку|общество|акционерное|публичное|непубличное|'
               r'с ограниченной ответственностью|государственное|'
               r'муниципальное|унитарное|предприятие|федеральное|бюджетное|'
               r'казённое|казенное|учреждение|образовательное|дошкольное)\b',
               ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


наши = set()
for r in e.execute('SELECT name FROM companies'):
    наши.add(норм(r[0]))

# добор свежих целей
видано = set()
if os.path.exists(ПОТОК):
    for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            видано.add(str(json.loads(ln).get('inn')))
        except Exception:  # noqa: BLE001
            pass
п = r'C:\seostat\drop\supplier_side_stream.jsonl'
if os.path.exists(п):
    for ln in io.open(п, encoding='utf-8', errors='replace'):
        try:
            видано.add(str(json.loads(ln).get('inn')))
        except Exception:  # noqa: BLE001
            pass
свежие = [r[0] for r in e.execute(
    'SELECT inn FROM companies ORDER BY COALESCE(pxr,0) DESC LIMIT 900')
    if r[0] not in видано][:20]
print(json.dumps({'старт': True, 'добираю': len(свежие)}, ensure_ascii=False))

ф = io.open(ПОТОК, 'a', encoding='utf-8')
for inn in свежие:
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        break
    try:
        r = EC.find_zakupki_supplier(inn, max_cards=6) or {}
    except Exception as ex:  # noqa: BLE001
        ф.write(json.dumps({'inn': inn, 'err': str(ex)[:120]},
                           ensure_ascii=False) + '\n')
        continue
    ф.write(json.dumps({'inn': inn, 'карточек': len(r.get('cards') or []),
                        'заказчики': sorted(set(x for x in
                                                (r.get('customers') or []) if x))},
                       ensure_ascii=False) + '\n')
    ф.flush()
    os.fsync(ф.fileno())
ф.close()

# сводим весь поток
компаний, с_карт, все_зак = 0, 0, {}
for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
    try:
        d = json.loads(ln)
    except Exception:  # noqa: BLE001
        continue
    if d.get('err'):
        continue
    компаний += 1
    if d.get('карточек'):
        с_карт += 1
    for имя in (d.get('заказчики') or []):
        c = чисто(имя)
        if len(c) > 8:
            все_зак.setdefault(c, set()).add(d.get('inn'))

пром = [k for k in все_зак if _ПРОМ.search(k) and not _БЮДЖЕТ.search(k)]
бюдж = [k for k in все_зак if _БЮДЖЕТ.search(k)]
прочие = [k for k in все_зак if k not in пром and k not in бюдж]
новые_пром = [k for k in пром if норм(k) not in наши]
print(json.dumps({'промышленные': sorted(пром)[:20]}, ensure_ascii=False)[:1200])
print(json.dumps({'прочие': sorted(прочие)[:14]}, ensure_ascii=False)[:900])
print(json.dumps({'компаний_прогнано': компаний, 'из_них_поставщики': с_карт,
                  'уникальных_заказчиков': len(все_зак),
                  'промышленных': len(пром), 'бюджетных': len(бюдж),
                  'прочих': len(прочие),
                  'промышленных_НЕТ_у_нас': len(новые_пром)},
                 ensure_ascii=False))
