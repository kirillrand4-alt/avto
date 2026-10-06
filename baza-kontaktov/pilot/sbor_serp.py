# -*- coding: utf-8 -*-
"""Сбор выдачи XMLRiver для пилота (ТЗ-PILOT-XMLRIVER.md, п. 2–3.1). Запускается НА СЕРВЕРЕ:
ключ XMLRIVER_USER/XMLRIVER_KEY берётся из окружения панели и никуда не печатается.

Параметры — по публичной документации XMLRiver (xmlriver.com/apiydoc, /apidoc):
  Яндекс: /search_yandex/xml  query, lr, groupby=10, page с 0, domain=ru|by, device=desktop
  Google: /search/xml         query, country, page с 1; с сентября 2025 отдаёт ровно 10 на страницу
Рабочий код сервера (serp_fetch.py, news_scan.col_xmlriver) гео не передаёт; lr и
country=2643 проверены пробой 05.10 (proba.py): выдача региональная.

Одно задание за раз, внутри 3 потока (как serp_fetch.py): лимит каналов аккаунта общий.
Результат — BAZA-PILOT-SERP.jsonl (fsync после каждого запроса, продолжение по qid+engine+page).

    python sbor_serp.py --proba            # 5 запросов на поисковик, 1 страница
    python sbor_serp.py --pages 5          # весь пилот, топ-50
"""
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.environ.get('BP_OUT', r'C:\sender\_ops\baza_pilot')
def _arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


SERP = os.path.join(OUT_DIR, _arg('--serp', 'BAZA-PILOT-SERP.jsonl'))
# ПРОВЕРИТЬ по справочнику стран XMLRiver (country — числовой id Google Ads geo).
THREADS = int(os.environ.get('BP_THREADS', 3))
GOOGLE_COUNTRY = {'ru': 2643, 'by': 2112}


def _url(engine, q, row, page):
    user, key = os.environ.get('XMLRIVER_USER', ''), os.environ.get('XMLRIVER_KEY', '')
    p = {'user': user, 'key': key, 'query': q, 'device': 'desktop'}
    # проба 05.10: groupby>10 игнорируется (10 на запрос), 0,025 ₽/запрос, ошибки не списываются
    if engine == 'yandex':
        p.update(lr=row['lr'], groupby=10, page=page, domain=('by' if row['country'] == 'by' else 'ru'))
        return 'http://xmlriver.com/search_yandex/xml?' + urllib.parse.urlencode(p)
    p.update(country=GOOGLE_COUNTRY[row['country']], page=page + 1)
    return 'http://xmlriver.com/search/xml?' + urllib.parse.urlencode(p)


def _text(el):
    return re.sub(r'\s+', ' ', ''.join(el.itertext())).strip() if el is not None else ''


def parse(body):
    """→ (docs[(url,title,snippet)], error|None). Формат Яндекс-XML: //doc/url, title, passages."""
    root = ET.fromstring(body)
    err = root.find('.//error')
    if err is not None:
        return [], f"{err.get('code', '')}: {_text(err)}"
    docs = []
    for d in root.iter('doc'):
        docs.append((_text(d.find('url')), _text(d.find('title')),
                     _text(d.find('passages')) or _text(d.find('headline'))))
    return docs, None


def fetch(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = f'{type(e).__name__}: {str(e)[:120]}'.replace(os.environ.get('XMLRIVER_KEY', '') or '\0', '***')
            time.sleep(5 * (i + 1))
    raise RuntimeError(last)


def main():
    proba = '--proba' in sys.argv
    pages = int(sys.argv[sys.argv.index('--pages') + 1]) if '--pages' in sys.argv else (1 if proba else 5)
    engines = ('yandex', 'google')
    rows = list(csv.DictReader(open(os.path.join(DIR, _arg('--zaprosy', 'pilot_zaprosy.csv')), encoding='utf-8')))
    if proba:
        rows = rows[::max(1, len(rows) // 5)][:5]
    os.makedirs(OUT_DIR, exist_ok=True)
    done = set()
    if os.path.exists(SERP):
        for line in open(SERP, encoding='utf-8'):
            try:
                j = json.loads(line)
                done.add((j['qid'], j['engine'], j['page']))
            except Exception:  # noqa: BLE001
                pass
    stat = {'zaprosov': 0, 'oshibok': 0, 'docs': 0, 'pusto': 0, 'povtorov': 0, 't0': time.time()}
    f = open(SERP, 'a', encoding='utf-8')
    lock = threading.Lock()

    def unit(row, eng):
        for pg in range(pages):
            if (row['qid'], eng, pg) in done:
                continue
            rec = {'qid': row['qid'], 'engine': eng, 'page': pg, 'query': row['query'],
                   'segment': row['segment'], 'subsegment': row['subsegment'],
                   'region': row['region'], 'ts': int(time.time())}
            for att in range(5):
                try:
                    body = fetch(_url(eng, row['query_full'], row, pg))
                    docs, err = parse(body)
                except Exception as e:  # noqa: BLE001
                    docs, err = [], str(e)[:200]
                # «Выполните перезапрос» / нет свободных каналов — транзиент, не списывается
                if not (err and re.search(r'перезапрос|свободных каналов|free channel', err, re.I)):
                    break
                with lock:
                    stat['povtorov'] += 1
                time.sleep(2 + 2 * att)
            rec['error'] = err
            rec['tries'] = att + 1
            rec['docs'] = [{'pos': pg * 10 + i + 1, 'url': u, 'title': t, 'snippet': s[:300]}
                           for i, (u, t, s) in enumerate(docs)]
            with lock:
                stat['zaprosov'] += 1
                stat['docs'] += len(docs)
                stat['oshibok'] += bool(err)
                stat['pusto'] += not docs
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
                if stat['zaprosov'] % 25 == 0:
                    print(time.strftime('%H:%M:%S'), json.dumps(stat, ensure_ascii=False), flush=True)
            if err or len(docs) < 8:
                break  # дальше страниц нет или канал ругается

    # 3 потока, как у серверного serp_fetch.py (WORKERS<=4): лимит каналов аккаунта общий
    with ThreadPoolExecutor(THREADS) as ex:
        list(ex.map(lambda a: unit(*a), [(r, e) for r in rows for e in engines]))
    f.close()
    stat['sek'] = round(time.time() - stat.pop('t0'))
    print('===ИТОГ===')
    print(json.dumps(stat, ensure_ascii=False))
    if proba:
        for line in open(SERP, encoding='utf-8').readlines()[-10:]:
            j = json.loads(line)
            print(j['engine'], j['qid'], j['error'], len(j['docs']), [d['url'] for d in j['docs'][:3]])


if __name__ == '__main__':
    main()
