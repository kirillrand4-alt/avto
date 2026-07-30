# -*- coding: utf-8 -*-
"""Один проход по базе обзвона -> durable-таблица base_ref в enrich.db.

Зачем. Проверки «телефон базы не совпал с телефоном сайта» и «правильные ли ИНН
у спасённых лидов» обе требуют ИСХОДНЫХ данных выгрузки (телефон, название,
адрес). Держать их только в памяти прогона нельзя — песочница откатывается, а
679-мегабайтный CSV читать заново дорого. Поэтому одна выжимка в enrich.db.

Что именно кладём (колонки выгрузки): [1] ИНН, [6] полное имя, [5] краткое,
[9] юрадрес, [18] телефоны через «|», [20] сайт, [34] выручка.

Запуск: python qc_baseref.py [--all]
  по умолчанию — только ИНН, которые есть в companies (9924);
  --all — все строки выгрузки (нужно для спот-чека спасённых, там ИНН могло
  не быть в companies... но он есть, ингестер их туда и пишет).
"""
import csv
import io
import json
import os
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB      # noqa: E402
import enrich_contacts as EC  # noqa: E402

ВСЕ = '--all' in sys.argv
ПОТОК = r'C:\seostat\drop\qc_baseref_stream.jsonl'
НАЧАЛО = time.time()

print(json.dumps({'ГОЛОВА': 'qc_baseref старт', 'все': ВСЕ}, ensure_ascii=False))
sys.stdout.flush()

db = EDB.EnrichDB()
e = db.cx
e.execute("""CREATE TABLE IF NOT EXISTS base_ref(
    inn TEXT PRIMARY KEY, name TEXT, name_short TEXT, addr TEXT,
    phones TEXT, site TEXT, revenue TEXT, updated_at TEXT)""")
e.commit()

путь = EC._find_base()
if not путь:
    print(json.dumps({'ошибка': 'база обзвона не найдена'}, ensure_ascii=False))
    os._exit(0)

нужны = None
if not ВСЕ:
    нужны = {str(r[0]) for r in e.execute('select inn from companies')}

INN, KRAT, POLN, ADDR, PHONES, SITE, REV = 1, 5, 6, 9, 18, 20, 34
try:
    csv.field_size_limit(2 ** 18)
except Exception:  # noqa: BLE001
    pass

o = {'строк_выгрузки': 0, 'записано': 0, 'с_телефоном': 0, 'с_сайтом': 0,
     'дублей_инн_в_выгрузке': 0}
ф = io.open(ПОТОК, 'a', encoding='utf-8')
видели = set()
пачка = []
with open(путь, encoding='utf-8-sig', newline='') as f:
    rd = csv.reader(f, delimiter=';')
    шапка = next(rd, None)
    o['шапка'] = [(i, (шапка[i] or '')[:28]) for i in (INN, KRAT, POLN, ADDR,
                                                       PHONES, SITE, REV)] if шапка else []
    while True:
        try:
            row = next(rd)
        except StopIteration:
            break
        except Exception:  # noqa: BLE001
            continue
        o['строк_выгрузки'] += 1
        if len(row) <= SITE:
            continue
        inn = (row[INN] or '').strip()
        if not inn:
            continue
        if нужны is not None and inn not in нужны:
            continue
        if inn in видели:
            o['дублей_инн_в_выгрузке'] += 1
            continue
        видели.add(inn)
        тел = [x.strip() for x in (row[PHONES] or '').split('|') if x.strip()]
        сайт = (row[SITE] or '').strip().split(' ')[0]
        пачка.append((inn, (row[POLN] or '').strip()[:250],
                      (row[KRAT] or '').strip()[:200],
                      (row[ADDR] or '').strip()[:300],
                      '|'.join(тел)[:400], сайт[:200],
                      (row[REV] or '').strip()[:30] if len(row) > REV else '',
                      db.now))
        if тел:
            o['с_телефоном'] += 1
        if сайт:
            o['с_сайтом'] += 1
        if len(пачка) >= 2000:
            e.executemany('INSERT OR REPLACE INTO base_ref'
                          '(inn,name,name_short,addr,phones,site,revenue,updated_at)'
                          ' VALUES(?,?,?,?,?,?,?,?)', пачка)
            e.commit()
            o['записано'] += len(пачка)
            ф.write(json.dumps({'записано': o['записано'],
                                'строк': o['строк_выгрузки']},
                               ensure_ascii=False) + '\n')
            ф.flush()
            os.fsync(ф.fileno())
            пачка = []
if пачка:
    e.executemany('INSERT OR REPLACE INTO base_ref'
                  '(inn,name,name_short,addr,phones,site,revenue,updated_at)'
                  ' VALUES(?,?,?,?,?,?,?,?)', пачка)
    e.commit()
    o['записано'] += len(пачка)
ф.write(json.dumps({'ИТОГ': o}, ensure_ascii=False) + '\n')
ф.flush()
os.fsync(ф.fileno())
ф.close()

o['сек'] = round(time.time() - НАЧАЛО)
o['в_base_ref'] = e.execute('select count(*) from base_ref').fetchone()[0]
o['в_base_ref_с_тел'] = e.execute(
    "select count(*) from base_ref where coalesce(phones,'')<>''").fetchone()[0]
o['пересечение_с_companies'] = e.execute(
    'select count(*) from base_ref b join companies c on c.inn=b.inn').fetchone()[0]
print(json.dumps(o, ensure_ascii=False, indent=1))
print(json.dumps({'ХВОСТ': 'qc_baseref готов', 'записано': o['записано'],
                  'в_base_ref': o['в_base_ref']}, ensure_ascii=False))
sys.stdout.flush()
os._exit(0)
