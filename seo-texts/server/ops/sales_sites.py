# -*- coding: utf-8 -*-
"""Слой 2 дообогащения базы продажников: телефоны/почты с САЙТОВ компаний и
страниц ЧЕКО — каждый контакт с URL страницы, где найден. Durable:
phone_contacts/emails + sales_sites3_stream.jsonl. Резюмируемо. 12 потоков
через socks5-прокси (:3001). Запуск: python sales_sites.py [бюджет_сек]"""
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
ПОТОК = r'C:\seostat\drop\sales_sites3_stream.jsonl'

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
цели = {}
for строки in БАЗА.values():
    for x in строки:
        i = str(x.get('inn') or '').strip()
        if i and i not in цели:
            цели[i] = {'их_тел': {re.sub(r'\D', '', str(t))[-10:]
                                  for t in (x.get('phones') or [])}}
row_map = {}
for i in list(цели):
    r = e.execute('SELECT site, ogrn FROM companies WHERE inn=?', (i,)).fetchone()
    row_map[i] = {'site': (r[0] if r else '') or '', 'ogrn': (r[1] if r else '') or ''}

сделано = set()
if os.path.exists(ПОТОК):
    for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            сделано.add(json.loads(ln)['inn'])
        except Exception:  # noqa: BLE001
            continue
todo = [i for i in цели if i not in сделано]

ТЕЛ = re.compile(r'(?:\+7|8)[\s(]*\d{3}[\s)]*[\d\s-]{7,10}')
ПОЧТА = re.compile(r'[\w.+-]+@[\w-]+\.[\w.]{2,10}')
замок = threading.Lock()
ф = io.open(ПОТОК, 'a', encoding='utf-8')
out = {'целей': len(todo), 'обработано': 0, 'тел_новых': 0, 'почт_новых': 0,
       'ошибок': 0}


def чист(т):
    ц = re.sub(r'\D', '', т)
    return ц[-10:] if len(ц) >= 10 else ''


def работа(t):
    idx, inn = t
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        return
    px = PX[idx % len(PX)]
    инфо = row_map.get(inn) or {}
    их = цели[inn]['их_тел']
    страницы = []
    сайт = (инфо.get('site') or '').strip()
    if сайт:
        б = сайт if сайт.startswith('http') else 'https://' + сайт
        страницы += [б, б + '/contacts', б + '/kontakty', б + '/contact']
    if инфо.get('ogrn'):
        страницы.append('https://checko.ru/company/%s' % инфо['ogrn'])
    найдено = {'inn': inn, 'тел': [], 'почта': []}
    for url in страницы:
        if time.time() - НАЧАЛО > БЮДЖЕТ:
            break
        try:
            r = requests.get(url, proxies={'http': px, 'https': px},
                             headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
            if r.status_code != 200:
                continue
            txt = r.text
        except Exception:  # noqa: BLE001
            continue
        ист = 'checko' if 'checko.ru' in url else 'сайт компании'
        for т in set(ТЕЛ.findall(txt)):
            ц = чист(т)
            if not ц or ц in их:
                continue
            их.add(ц)
            найдено['тел'].append((т.strip(), ист, url))
        if 'checko.ru' not in url:
            дом_с = re.sub(r'^https?://(www\.)?', '', сайт).split('/')[0]
            for п in set(ПОЧТА.findall(txt)):
                if дом_с and п.lower().endswith('@' + дом_с):
                    найдено['почта'].append((п.lower(), url))
    with замок:
        ts = time.strftime('%Y-%m-%dT%H:%M:%S')
        for т, ист, url in найдено['тел']:
            e.execute('INSERT OR REPLACE INTO phone_contacts VALUES (?,?,?,?,?,?,?)',
                      (inn, т, '', 'общий (со страницы)', ист, url, ts))
            out['тел_новых'] += 1
        for п, url in set(найдено['почта']):
            try:
                e.execute("INSERT OR IGNORE INTO emails(inn,email,role,person,"
                          "source,source_url,updated_at) VALUES(?,?,?,?,?,?,?)",
                          (inn, п, '', '', 'site', url, ts))
                out['почт_новых'] += 1
            except Exception:  # noqa: BLE001
                pass
        e.commit()
        ф.write(json.dumps({'inn': inn, 'тел': len(найдено['тел']),
                            'почт': len(набор) if (набор := set(найдено['почта'])) or True else 0},
                           ensure_ascii=False) + '\n')
        ф.flush()
        out['обработано'] += 1


with ThreadPoolExecutor(max_workers=50) as пул:
    list(пул.map(работа, enumerate(todo)))
ф.close()
print(json.dumps(out, ensure_ascii=False, indent=1)[:1200])
