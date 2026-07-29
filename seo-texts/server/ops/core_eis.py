# -*- coding: utf-8 -*-
"""Дообогащение базы продажников, приоритет — ТЕЛЕФОНЫ ЗАКУПЩИКОВ из ЕИС
(владелец 27.07: «максимум дообогащения, обязательно с кликабельной ссылкой»).

Механика: find_zakupki_contacts (RSS ЕИС по ИНН -> карточка закупки -> блок
«Контактная информация»: ФИО+тел+почта снабженца + URL карточки).
DURABLE: enrich.phone_contacts (новая таблица с source_url) + emails(+source_url)
+ поток core_eis_stream.jsonl на drop. Резюмируемо: сделанные ИНН скипаются.
Параллельность скромная (5) — ЕИС ходим напрямую, банить нельзя.
Запуск: python sales_eis.py [бюджет_сек]"""
import io
import json
import os
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB
import enrich_contacts as EC

БЮДЖЕТ = float(sys.argv[1]) if len(sys.argv) > 1 else 480.0
НАЧАЛО = time.time()
ПОТОК = r'C:\seostat\drop\core_eis_stream.jsonl'

db = EDB.EnrichDB()
e = db.cx
e.execute("""CREATE TABLE IF NOT EXISTS phone_contacts(
    inn TEXT, phone TEXT, person TEXT, role TEXT,
    source TEXT, source_url TEXT, updated_at TEXT,
    PRIMARY KEY (inn, phone, source_url))""")
e.commit()

инны = []
for ln in io.open(r'C:\seostat\drop\drop-storage\centrifugal-core-inns.txt',
                  encoding='utf-8', errors='replace'):
    m = __import__('re').search(r'\b(\d{10}|\d{12})\b', ln)
    if m and m.group(1) not in инны:
        инны.append(m.group(1))

сделано = set()
if os.path.exists(ПОТОК):
    for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            сделано.add(json.loads(ln)['inn'])
        except Exception:  # noqa: BLE001
            continue
todo = [i for i in инны if i not in сделано]

замок = threading.Lock()
ф = io.open(ПОТОК, 'a', encoding='utf-8')
out = {'в_базе_инн': len(инны), 'было_сделано': len(сделано),
       'обработано': 0, 'телефонов': 0, 'почт': 0, 'ошибок': 0, 'примеры': []}


def работа(inn):
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        return
    try:
        z = EC.find_zakupki_contacts(inn, max_cards=4)
    except Exception as ex:  # noqa: BLE001
        z = {'inn': inn, 'error': repr(ex)[:80]}
    with замок:
        ф.write(json.dumps(z or {'inn': inn}, ensure_ascii=False) + '\n')
        ф.flush()
        out['обработано'] += 1
        if not z or z.get('error'):
            out['ошибок'] += 1
            return
        for c in (z.get('cards') or []):
            ts = time.strftime('%Y-%m-%dT%H:%M:%S')
            if c.get('phone'):
                e.execute("INSERT OR REPLACE INTO phone_contacts VALUES "
                          "(?,?,?,?,?,?,?)",
                          (inn, c['phone'], c.get('contact_person') or '',
                           'закупки (контакт из карточки закупки)',
                           'zakupki:eis', c.get('url') or '', ts))
                out['телефонов'] += 1
                if len(out['примеры']) < 6:
                    out['примеры'].append({'инн': inn, 'тел': c['phone'],
                                           'кто': c.get('contact_person'),
                                           'url': (c.get('url') or '')[:70]})
            if c.get('email'):
                try:
                    db.upsert_email(inn, c['email'],
                                    role='закупки', person=c.get('contact_person') or '',
                                    source='zakupki:eis',
                                    source_url=c.get('url') or '')
                    out['почт'] += 1
                except Exception:  # noqa: BLE001
                    try:
                        e.execute(
                            "INSERT OR IGNORE INTO emails(inn,email,role,person,"
                            "source,source_url,updated_at) VALUES(?,?,?,?,?,?,?)",
                            (inn, c['email'], 'закупки',
                             c.get('contact_person') or '', 'zakupki:eis',
                             c.get('url') or '', ts))
                        out['почт'] += 1
                    except Exception:  # noqa: BLE001
                        pass
        e.commit()


with ThreadPoolExecutor(max_workers=5) as пул:
    list(пул.map(работа, todo))
ф.close()
out['осталось'] = len(todo) - out['обработано']
print(json.dumps(out, ensure_ascii=False, indent=1)[:1800])
