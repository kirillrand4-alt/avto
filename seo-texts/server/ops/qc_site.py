# -*- coding: utf-8 -*-
"""Один обход сайта — два признака: телефоны НА САЙТЕ и год копирайта.

Зачем вместе. Обе проверки («телефон базы не встретился на сайте» и «сайт не
обновлялся с 2019») читают одну и ту же главную страницу. Отдельными прогонами
это два обхода вместо одного.

ЧТО ИМЕННО ПИШЕМ (и что эти величины НЕ значат):
  * `phones`  — десятизначные номера, найденные ЕДИНОЙ боевой функцией
    EC.phones_in по разметке, из которой вырезаны SVG/скрипты/стили
    (EC.без_графики). Это «номера, которые встретились на скачанных нами
    страницах», а НЕ «все номера компании»: страниц берём максимум две.
  * `cr_year` — МАКСИМАЛЬНЫЙ год в окне ±60 символов вокруг знака копирайта
    (©, &copy;, (c), copyright). Максимум, а не первый: «© 2005-2026» означает
    свежий сайт, а первый год там 2005.
  * `js_year` — на странице есть getFullYear()/new Date(): год подставляется
    скриптом, и наш статический забор его НЕ ВИДИТ. Такие сайты нельзя
    записывать в «года нет» — по ним признак свежести просто не работает.
  * `http`/`err` — скачалась ли страница вообще. Без этого «телефона нет на
    сайте» неотличимо от «сайт не открылся», а это разные вещи.

Durable: таблица qc_site в enrich.db + qc_site_stream.jsonl с fsync.
Резюм: ИНН с непустым checked_at пропускается.

Запуск: python qc_site.py [бюджет_сек] [потоков] [--recheck] [--limit N]
"""
import io
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB      # noqa: E402
import enrich_contacts as EC  # noqa: E402

EC._NO_BROWSER = True        # без тяжёлого браузерного фолбэка: время на компанию

_поз = [a for a in sys.argv[1:] if not a.startswith('--')]
БЮДЖЕТ = float(_поз[0]) if _поз else 320.0
ПОТОКОВ = int(_поз[1]) if len(_поз) > 1 else 16
ПЕРЕПРОВЕРКА = '--recheck' in sys.argv
ЛИМИТ = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else 0
НАЧАЛО = time.time()
ПОТОК = r'C:\seostat\drop\qc_site_stream.jsonl'

print(json.dumps({'ГОЛОВА': 'qc_site старт', 'бюджет': БЮДЖЕТ, 'потоков': ПОТОКОВ},
                 ensure_ascii=False))
sys.stdout.flush()

db = EDB.EnrichDB()
e = db.cx
e.execute("""CREATE TABLE IF NOT EXISTS qc_site(
    inn TEXT PRIMARY KEY, url TEXT, http INTEGER, nbytes INTEGER, npages INTEGER,
    phones TEXT, n_phones INTEGER, cr_year INTEGER, cr_marker INTEGER,
    js_year INTEGER, years_all TEXT, err TEXT, checked_at TEXT)""")
e.commit()

# очередь: компании с сайтом. Приоритет — те, у кого В БАЗЕ ЕСТЬ ТЕЛЕФОН
# (без него проверка №2 неприменима), дальше остальные.
готово = set() if ПЕРЕПРОВЕРКА else {
    r[0] for r in e.execute("select inn from qc_site where coalesce(checked_at,'')<>''")}
очередь = []
for inn, site, есть_тел in e.execute(
        "select c.inn, c.site, case when coalesce(b.phones,'')<>'' then 1 else 0 end "
        'from companies c left join base_ref b on b.inn=c.inn '
        "where coalesce(c.site,'')<>'' order by 3 desc, c.inn"):
    if str(inn) in готово:
        continue
    очередь.append((str(inn), site))
if ЛИМИТ:
    очередь = очередь[:ЛИМИТ]

o = {'в_очереди': len(очередь), 'обработано': 0, 'скачано': 0, 'пусто': 0,
     'с_телефонами': 0, 'с_годом': 0, 'js_год': 0}
замок = threading.Lock()
ф = io.open(ПОТОК, 'a', encoding='utf-8')

_КОНТАКТ = re.compile(
    r'href\s*=\s*["\']([^"\']{1,120}?(?:contact|kontakt|kontakty|контакт|'
    r'o-kompanii|about|rekvizit)[^"\']{0,40})["\']', re.I)
_МАРКЕР = re.compile(r'©|&copy;|&#169;|\(c\)\s*20|copyright', re.I)
_ГОД = re.compile(r'\b(19[89]\d|20[0-4]\d)\b')
_JSГОД = re.compile(r'getFullYear|new\s+Date\s*\(', re.I)


def _норм(с):
    ц = re.sub(r'\D', '', с or '')
    if len(ц) == 11 and ц[0] in '78':
        ц = ц[1:]
    return ц if len(ц) == 10 else ''


def _тянуть(u, tmo=18):
    """Прямая закачка. Возврат (html, http_код, ошибка)."""
    try:
        req = urllib.request.Request(u, headers={
            'User-Agent': EC.VC.UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
            'Accept': 'text/html,application/xhtml+xml'})
        with EC._DIRECT.open(req, timeout=tmo) as r:
            try:
                raw = r.read(1200000)
            except Exception as ex:  # noqa: BLE001
                raw = getattr(ex, 'partial', b'') or b''
            return EC._раскодировать(raw, r.headers.get('Content-Type', '')), \
                getattr(r, 'status', 200) or 200, ''
    except urllib.error.HTTPError as ex:  # noqa: BLE001
        try:
            h = EC._раскодировать(ex.read(300000), '')
        except Exception:  # noqa: BLE001
            h = ''
        return h, ex.code, 'HTTP%s' % ex.code
    except Exception as ex:  # noqa: BLE001
        return '', 0, type(ex).__name__ + ':' + str(ex)[:60]


def годы(html):
    """(макс_год_у_копирайта, есть_маркер, есть_js_год, все_годы_у_маркера)."""
    t = EC.без_графики(html or '')
    js = 1 if _JSГОД.search(html or '') else 0
    найдено = []
    маркер = 0
    for m in _МАРКЕР.finditer(t):
        маркер = 1
        окно = t[max(0, m.start() - 60):m.end() + 60]
        найдено += [int(g) for g in _ГОД.findall(окно)]
        if len(найдено) > 40:
            break
    return (max(найдено) if найдено else None), маркер, js, sorted(set(найдено))[-6:]


def работа(зад):
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        return
    inn, site = зад
    u = site if str(site).startswith(('http://', 'https://')) else 'http://' + str(site)
    html, код, ошибка = _тянуть(u)
    страниц = 1 if html else 0
    if not html or EC._looks_blocked(html):
        # один вежливый фолбэк через прокси/решатель, дальше не мучаем
        try:
            h2, _m2, _mt = EC.VC._fetch(u)
            if h2:
                html, страниц = h2, 1
                ошибка = ошибка or 'через_прокси'
        except Exception:  # noqa: BLE001
            pass
    полный = html or ''
    # вторая страница — контакты (там телефоны, которых нет в шапке)
    if html:
        m = _КОНТАКТ.search(html)
        if m and time.time() - НАЧАЛО < БЮДЖЕТ:
            ссыл = urllib.parse.urljoin(u, m.group(1))
            if ссыл != u and len(ссыл) < 300:
                h2, _к2, _о2 = _тянуть(ссыл, tmo=14)
                if h2:
                    полный += '\n' + h2
                    страниц += 1
    тел = sorted({_норм(mm.group(0)) for mm in EC.phones_in(EC.без_графики(полный))})
    тел = [t for t in тел if t]
    год, маркер, js, все = годы(полный)
    зап = (inn, u, код, len(полный), страниц, '|'.join(тел), len(тел),
           год, маркер, js, ','.join(str(x) for x in все), (ошибка or '')[:110],
           db.now)
    with замок:
        e.execute('INSERT OR REPLACE INTO qc_site(inn,url,http,nbytes,npages,'
                  'phones,n_phones,cr_year,cr_marker,js_year,years_all,err,'
                  'checked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', зап)
        o['обработано'] += 1
        if полный:
            o['скачано'] += 1
        else:
            o['пусто'] += 1
        if тел:
            o['с_телефонами'] += 1
        if год:
            o['с_годом'] += 1
        if js:
            o['js_год'] += 1
        if o['обработано'] % 20 == 0:
            e.commit()
        ф.write(json.dumps({'inn': inn, 'url': u, 'http': код, 'байт': len(полный),
                            'тел': len(тел), 'год': год, 'js': js,
                            'err': (ошибка or '')[:40]}, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())


with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
    list(пул.map(работа, очередь))
e.commit()
ф.close()

o['сек'] = round(time.time() - НАЧАЛО)
o['всего_в_qc_site'] = e.execute('select count(*) from qc_site').fetchone()[0]
o['осталось'] = e.execute(
    "select count(*) from companies c where coalesce(c.site,'')<>'' "
    'and c.inn not in (select inn from qc_site)').fetchone()[0]
print(json.dumps(o, ensure_ascii=False, indent=1))
print(json.dumps({'ХВОСТ': 'qc_site круг готов', 'обработано': o['обработано'],
                  'всего': o['всего_в_qc_site'], 'осталось': o['осталось'],
                  'сек': o['сек']}, ensure_ascii=False))
sys.stdout.flush()
os._exit(0)
