# -*- coding: utf-8 -*-
"""Дообнаружение по базе продажников: страница чеко для КАЖДОГО из 555 ИНН ->
сайт компании + название + телефоны (+выручка бонусом). Компании, которых нет
в enrich, ЗАВОДЯТСЯ (durable). Провенанс: checko-URL. Резюмируемо.
Запуск: python sales_discover.py [бюджет_сек]"""
import io
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import requests

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB

БЮДЖЕТ = float(sys.argv[1]) if len(sys.argv) > 1 else 480.0
НАЧАЛО = time.time()
ПОТОК = r'C:\seostat\drop\sales_discover2_stream.jsonl'

db = EDB.EnrichDB()
e = db.cx
e.execute("""CREATE TABLE IF NOT EXISTS phone_contacts(
    inn TEXT, phone TEXT, person TEXT, role TEXT,
    source TEXT, source_url TEXT, updated_at TEXT,
    PRIMARY KEY (inn, phone, source_url))""")
e.commit()

d = urllib.request.build_opener(urllib.request.ProxyHandler({}))
req = urllib.request.Request(
    os.environ.get('DROP_URL', '').rstrip('/') + '/dolphin-proxies.txt',
    headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
PX = []
for l in d.open(req, timeout=30).read().decode('utf-8', 'replace').splitlines():
    l = l.strip()
    m = re.match(r'(?:([^:@]+):([^@]*)@)?([^:/]+):(\d+)', l) if l and not l.startswith('#') else None
    if m:
        u, p, h, _ = m.groups()
        PX.append('socks5://%s:%s@%s:3001' % (u, p, h))

БАЗА = json.load(open(r'C:\sender\_ops\sales_base.json', encoding='utf-8'))
инны, имена = [], {}
for строки in БАЗА.values():
    for x in строки:
        i = str(x.get('inn') or '').strip()
        if i and i not in инны:
            инны.append(i)
            имена[i] = str(x.get('name') or '')[:120]

сделано = set()
if os.path.exists(ПОТОК):
    for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            сделано.add(str(json.loads(ln)['inn']))
        except Exception:  # noqa: BLE001
            continue
todo = [i for i in инны if i not in сделано]

ТЕЛ = re.compile(r'(?:\+7|8)[\s(]*\d{3}[\s)]*[\d\s-]{7,10}')
МН = {'млрд': 1e9, 'млн': 1e6, 'тыс': 1e3}
замок = threading.Lock()
ф = io.open(ПОТОК, 'a', encoding='utf-8')
out = {'целей': len(todo), 'обработано': 0, 'сайт_найден': 0, 'тел': 0,
       'выручка': 0, 'заведено_в_enrich': 0, 'ошибок': 0}


def работа(t):
    idx, inn = t
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        return
    px = PX[idx % len(PX)]
    # /search?query=ИНН сам редиректит на карточку (проверено пробником;
    # прямой /company/ИНН даёт 404 - там слаг «имя-огрн»)
    url = 'https://checko.ru/search?query=%s' % inn
    try:
        r = requests.get(url, proxies={'http': px, 'https': px},
                         headers={'User-Agent': 'Mozilla/5.0'}, timeout=25,
                         allow_redirects=True)
        if r.status_code != 200 or 'checko.ru/company' not in str(r.url):
            raise RuntimeError('нет карточки (%s)' % r.status_code)
        html = r.text
        фин_url = str(r.url)
    except Exception as ex:  # noqa: BLE001
        with замок:
            ф.write(json.dumps({'inn': inn, 'err': repr(ex)[:60]},
                               ensure_ascii=False) + '\n')
            ф.flush()
            out['ошибок'] += 1
            out['обработано'] += 1
        return
    txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))
    # сайт: ссылка вида >example.ru< возле метки «Сайт»
    сайт = ''
    m = re.search(r'Сайт[^а-яА-Я]{0,80}?([a-z0-9а-яё-]+(?:\.[a-zа-яё-]+)+)',
                  txt, re.I)
    if m and 'checko' not in m.group(1):
        сайт = m.group(1).lower()
    телефоны = list(dict.fromkeys(ТЕЛ.findall(txt)))[:4]
    выр, год = 0, ''
    mv = re.search(r'Выручка компании за (\d{4}) год составила ([\d.,]+)\s*'
                   r'(млрд|млн|тыс)?', txt)
    if mv:
        try:
            выр = float(mv.group(2).replace(',', '.')) * МН.get(mv.group(3) or '', 1)
            год = mv.group(1)
            if выр < 100000:
                выр = 0
        except ValueError:
            выр = 0
    with замок:
        есть = e.execute('SELECT 1 FROM companies WHERE inn=?', (inn,)).fetchone()
        if not есть:
            e.execute('INSERT OR IGNORE INTO companies(inn, name) VALUES(?,?)',
                      (inn, имена.get(inn) or ''))
            out['заведено_в_enrich'] += 1
        if сайт:
            e.execute("UPDATE companies SET site=COALESCE(NULLIF(site,''),?) "
                      "WHERE inn=?", (сайт, inn))
            out['сайт_найден'] += 1
        if выр:
            e.execute('UPDATE companies SET revenue_rub=?, revenue_year=? '
                      'WHERE inn=? AND revenue_rub IS NULL', (int(выр), год, inn))
            out['выручка'] += 1
        ts = time.strftime('%Y-%m-%dT%H:%M:%S')
        for тел in телефоны:
            e.execute('INSERT OR REPLACE INTO phone_contacts VALUES (?,?,?,?,?,?,?)',
                      (inn, тел.strip(), '', 'общий (чеко)', 'checko', фин_url, ts))
            out['тел'] += 1
        e.commit()
        ф.write(json.dumps({'inn': inn, 'site': сайт, 'тел': len(телефоны),
                            'выр': int(выр)}, ensure_ascii=False) + '\n')
        ф.flush()
        out['обработано'] += 1


with ThreadPoolExecutor(max_workers=15) as пул:
    list(пул.map(работа, enumerate(todo)))
ф.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
