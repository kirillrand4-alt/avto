# -*- coding: utf-8 -*-
"""Слой «Контактная информация» чеко для ОБЕИХ баз (продажники 555 + ядро 396):
страница /contacts карточки — блок «Телефоны» (форматированные номера) и
«Электронная почта». Каждый контакт с URL этой страницы. Жёсткий валидатор.
Резюмируемо: checko_contacts2_stream.jsonl. 50 потоков, socks5:3001.
Запуск: python checko_contacts.py [бюджет_сек]"""
import io
import json
import os
import re
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
ПОТОК = r'C:\seostat\drop\checko_contacts2_stream.jsonl'

db = EDB.EnrichDB()
e = db.cx

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

инны = []
БАЗА = json.load(open(r'C:\sender\_ops\sales_base.json', encoding='utf-8'))
for строки in БАЗА.values():
    for x in строки:
        i = str(x.get('inn') or '').strip()
        if i and i not in инны:
            инны.append(i)
for ln in io.open(r'C:\seostat\drop\drop-storage\centrifugal-core-inns.txt',
                  encoding='utf-8', errors='replace'):
    m = re.search(r'\b(\d{10}|\d{12})\b', ln)
    if m and m.group(1) not in инны:
        инны.append(m.group(1))

сделано = set()
if os.path.exists(ПОТОК):
    for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            сделано.add(str(json.loads(ln)['inn']))
        except Exception:  # noqa: BLE001
            continue
todo = [i for i in инны if i not in сделано]

ogrn = {}
for i, o in e.execute("SELECT inn, ogrn FROM companies WHERE COALESCE(ogrn,'')<>''"):
    ogrn[str(i)] = str(o)
try:
    ix = __import__('sqlite3').connect(r'C:\sender\obzvon-index.db')
    for i, o in ix.execute("SELECT inn, ogrn FROM obzvon WHERE COALESCE(ogrn,'')<>''"):
        ogrn.setdefault(str(i), str(o))
except Exception:  # noqa: BLE001
    pass

ТЕЛ_ФОРМ = re.compile(r'\+7[\s\u00a0]?\(?\d{3}\)?[\s\u00a0]?\d{3}[-\s\u00a0]\d{2}[-\s\u00a0]\d{2}')
ПОЧТА = re.compile(r'[\w.+-]+@[\w-]+\.[\w.]{2,10}')


def валиден(s):
    ц = re.sub(r'\D', '', s)
    if len(ц) == 11 and ц[0] in '78':
        ц = ц[1:]
    return (len(ц) == 10 and ц[0] != '0' and ц[:3] != '000'
            and len(set(ц)) > 2 and len(set(ц[3:])) > 1)


замок = threading.Lock()
ф = io.open(ПОТОК, 'a', encoding='utf-8')
out = {'целей': len(todo), 'обработано': 0, 'тел': 0, 'почт': 0, 'ошибок': 0,
       'без_карточки': 0}


def работа(t):
    idx, inn = t
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        return
    px = PX[idx % len(PX)]
    ог = ogrn.get(inn)
    urls = []
    if ог:
        urls.append('https://checko.ru/company/%s/contacts' % ог)
    urls.append('https://checko.ru/search?query=%s' % inn)
    html, фин = '', ''
    for u in urls:
        try:
            r = requests.get(u, proxies={'http': px, 'https': px},
                             headers={'User-Agent': 'Mozilla/5.0'}, timeout=25,
                             allow_redirects=True)
            if r.status_code != 200 or '/company/' not in str(r.url):
                continue
            фин = str(r.url)
            if not фин.rstrip('/').endswith('/contacts'):
                # с поиска попали на карточку - дотягиваем /contacts
                база = фин.split('?')[0].rstrip('/')
                r2 = requests.get(база + '/contacts',
                                  proxies={'http': px, 'https': px},
                                  headers={'User-Agent': 'Mozilla/5.0'},
                                  timeout=25)
                if r2.status_code == 200:
                    фин = база + '/contacts'
                    html = r2.text
                    break
            html = r.text
            break
        except Exception:  # noqa: BLE001
            continue
    with замок:
        out['обработано'] += 1
        if not html:
            out['без_карточки'] += 1
            ф.write(json.dumps({'inn': inn, 'err': 'нет карточки'},
                               ensure_ascii=False) + '\n')
            ф.flush()
            return
        # блок «Контактная информация»: телефоны только форматированные
        чистый = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html,
                        flags=re.S | re.I)
        # обрезаем подвал (реклама/др. компании) по маркеру формы правки
        m = re.search(r'(.*?)(Нашли ошибку в контактах|Предложить исправление|'
                      r'Похожие компании|Портал .Чекко)', чистый, re.S)
        основа = m.group(1) if m else чистый
        # телефоны берём из блока «Телефоны», почты из «Электронная почта»
        текст = re.sub(r'<[^>]+>', ' ', основа)
        телефоны = [т for т in dict.fromkeys(ТЕЛ_ФОРМ.findall(текст))
                    if валиден(т)][:30]
        # почты: только href mailto ИЛИ явные адреса из блока (без чужих
        # доменов площадки)
        mail_href = re.findall(r'mailto:([\w.+-]+@[\w.-]+)', основа)
        почты_все = list(dict.fromkeys(
            [p.lower() for p in mail_href]
            + [p.lower() for p in ПОЧТА.findall(текст)]))
        почты = [p for p in почты_все
                 if 'checko' not in p and not p.endswith('.png')
                 and not p.endswith('.jpg')][:30]
        ts = time.strftime('%Y-%m-%dT%H:%M:%S')
        for т in телефоны:
            e.execute('INSERT OR REPLACE INTO phone_contacts VALUES (?,?,?,?,?,?,?)',
                      (inn, т, '', 'контакты компании (чеко)',
                       'checko:contacts', фин, ts))
            out['тел'] += 1
        for п in почты:
            e.execute("INSERT OR IGNORE INTO emails(inn,email,role,person,"
                      "source,source_url,updated_at) VALUES(?,?,?,?,?,?,?)",
                      (inn, п, '', '', 'checko:contacts', фин, ts))
            out['почт'] += 1
        e.commit()
        ф.write(json.dumps({'inn': inn, 'тел': len(телефоны),
                            'почт': len(почты)}, ensure_ascii=False) + '\n')
        ф.flush()


with ThreadPoolExecutor(max_workers=50) as пул:
    list(пул.map(работа, enumerate(todo)))
ф.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
