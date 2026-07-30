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
import enrich_contacts as EC  # общий разбор телефонов, см. phones_in

_поз = [a for a in sys.argv[1:] if not a.startswith('--')]
БЮДЖЕТ = float(_поз[0]) if _поз else 480.0
НАЧАЛО = time.time()
# Имя потока сменное. Нужно для ПЕРЕКРАУЛИВАНИЯ: старый поток помнит все 555
# как сделанные, и прогон с починенной кодировкой не тронул бы ни одной
# компании — молча отчитавшись «целей 0». Новый поток = чистый заход, при
# этом старый остаётся как история.
ПОТОК = (sys.argv[sys.argv.index('--поток') + 1] if '--поток' in sys.argv
         else r'C:\seostat\drop\sales_sites3_stream.jsonl')

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

# Своей регулярки телефона здесь БОЛЬШЕ НЕТ. Она была слабее боевой сразу
# вдвойне: без (?<!\d) выкусывала номер из середины ОГРН в подвале сайта,
# и требовала код ровно из трёх цифр, теряя «8 (3812) 39-45-67». Берём
# EC.phones_in — ту же точку, что и весь остальной конвейер.
ТЕЛ = None  # см. EC.phones_in
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
            # НЕ r.text. requests, не найдя charset в заголовке, по букве
            # HTTP считает text/html латиницей-1 — и на windows-1251 сайте
            # кириллица гибнет ДО разбора: «Главный энергетик» превращается в
            # мусор, окно вокруг телефона теряет должность, а страница
            # выглядит успешно скачанной. Общий декодер уже умеет выбирать
            # кодировку по заголовку, мете и доле кириллицы — этот оп ходил
            # мимо него своим фетчем и починку 29.07 не получил.
            txt = EC.без_графики(
                EC._раскодировать(r.content, r.headers.get('Content-Type', '')))
        except Exception:  # noqa: BLE001
            continue
        ист = 'checko' if 'checko.ru' in url else 'сайт компании'
        for т in {m.group(0) for m in EC.phones_in(txt)}:
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
            # Через add_phone, а не своим INSERT: там рубеж против реквизитов
            # (ИНН, разложенный по маске телефона, однажды доехал до панели
            # как «+7 (500) 100-00-66») и защита известной роли от понижения.
            # Раньше здесь стоял `INSERT OR IGNORE` — он роль не ронял, но и
            # рубежа не видел, потому что рубеж живёт в писателе, а этот слой
            # писал мимо него.
            if db.add_phone(inn, т, role='общий (со страницы)', source=ист,
                            source_url=url):
                out['тел_новых'] += 1
            else:
                out['тел_отсеяно'] = out.get('тел_отсеяно', 0) + 1
        for п, url in set(найдено['почта']):
            try:
                # add_email, а не сырой INSERT: он канонизирует роль и не
                # понижает уже известную. Сырая вставка клала role='' и потом
                # мешала апгрейду адреса до точной роли.
                db.add_email(inn, п, role='', person='', source='сайт компании',
                             source_url=url)
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
