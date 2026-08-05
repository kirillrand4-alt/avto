# -*- coding: utf-8 -*-
"""Два пути к hh: сломанный в конвейере новостей и рабочий рядом. Проверяю оба.

Владелец: «в инструменте вроде не было апи hh, а сейчас он есть на сервере». Из патчей
`patch_hh_vacancy_scan_v3/v4` видно почему — там записано прямым текстом:

    «api.hh.ru отдаёт 403 без токена приложения, поэтому берём человеческую выдачу
     hh.ru/search/vacancy через дельфин-профиль с мобильным IP»

А `col_hh` в `news_scan.py` ходит ровно в `api.hh.ru/vacancies`. Отсюда и мой «источник
реально пуст: 0 сырых» — источник не пуст, к нему ведёт сломанный путь, а рабочий лежит
в соседнем файле и в новостном прогоне не зовётся.

ЧТО ПРОВЕРЯЮ (ничего не запускаю тяжёлого, только смотрю):
  1. что именно возвращает `api.hh.ru` сейчас — код ответа, а не «пусто»;
  2. есть ли в живом `enrich_contacts.py` блок `hh_vacancy_scan` и какой он версии;
  3. когда последний раз приходили сигналы `hh-вакансия` и сколько их —
     то есть работал ли рабочий путь и когда;
  4. и сколько из них ПРЯМЫХ, чтобы число «445 из 445» было проверенным, а не моим.
"""
import collections
import io
import json
import os
import re
import sqlite3
import sys
import urllib.request

sys.path.insert(0, r'C:\sender\server')

BAZA = r'C:\sender\enrich.db'
ENRICH = r'C:\sender\server\enrich_contacts.py'
MASHINA = re.compile(
    r'компрессор\w*|турбокомпрессор\w*|газодувк\w+|воздуходувк\w+|нагнетател\w+|'
    r'воздухоразделен\w+|\bВРУ\b|сжат\w+\s+воздух\w*|пневмат\w+|'
    r'генератор\w*\s+(?:азота|кислорода)|\bазот\w*\b|\bкислород\w*\b|\bчиллер\w*', re.I)

print('=== 1. ЧТО ОТВЕЧАЕТ api.hh.ru ПРЯМО СЕЙЧАС')
url = ('https://api.hh.ru/vacancies?text=%22%D0%BC%D0%B0%D1%88%D0%B8%D0%BD%D0%B8%D1%81'
       '%D1%82%20%D0%BA%D0%BE%D0%BC%D0%BF%D1%80%D0%B5%D1%81%D1%81%D0%BE%D1%80%D0%BD%D1'
       '%8B%D1%85%20%D1%83%D1%81%D1%82%D0%B0%D0%BD%D0%BE%D0%B2%D0%BE%D0%BA%22'
       '&per_page=5&area=113')
try:
    r = urllib.request.urlopen(urllib.request.Request(
        url, headers={'Accept': 'application/json'}), timeout=25)
    body = r.read()[:400]
    print('  код %s, тело: %s' % (r.getcode(), body[:220]))
except Exception as e:  # noqa: BLE001
    print('  ОШИБКА: %s: %s' % (type(e).__name__, str(e)[:220]))

print('\n=== 2. ЕСТЬ ЛИ РАБОЧИЙ ПУТЬ В ЖИВОМ enrich_contacts.py')
if os.path.exists(ENRICH):
    t = io.open(ENRICH, encoding='utf-8', errors='replace').read()
    print('  файл %s, знаков %d' % (ENRICH, len(t)))
    for marker in ('hh_vacancy_scan', 'hhscan_v4', 'hhscan_v3', 'hh.ru/search/vacancy',
                   'dolphin_start'):
        print('  %-24s встречается %d раз' % (marker, t.count(marker)))
    i = t.find("args.get('op') == 'hh_vacancy_scan'")
    if i > 0:
        print('\n  --- первые 40 строк блока:')
        for l in t[i:i + 3200].split('\n')[:40]:
            print('   %s' % l[:150])
else:
    print('  файла нет')

print('\n=== 3. КОГДА РАБОТАЛ РАБОЧИЙ ПУТЬ (сигналы hh-вакансия)')
if os.path.exists(BAZA):
    cx = sqlite3.connect('file:%s?mode=ro' % BAZA.replace('\\', '/'), uri=True)
    for ist, n, mn, mx in cx.execute(
            "select source, count(*), min(updated_at), max(updated_at) from signals"
            " where source like '%hh%' group by source"):
        print('  %-16s %5d   с %s   по %s' % (ist, n, str(mn)[:19], str(mx)[:19]))
    sch = collections.Counter()
    primery = []
    for ist, what, url_ in cx.execute(
            "select source, what, source_url from signals where source like '%hh%'"):
        pryamoy = bool(MASHINA.search(what or ''))
        sch['%s | %s' % (ist, 'ПРЯМОЙ' if pryamoy else 'без машины')] += 1
        if pryamoy and len(primery) < 8:
            primery.append((ist, what, url_))
    print('\n  --- прямые и непрямые по каждому источнику hh')
    for k, v in sch.most_common():
        print('    %-34s %5d' % (k, v))
    print('\n  --- 8 прямых глазами')
    for ist, what, url_ in primery:
        print('    [%s] %s' % (ist, re.sub(r'\s+', ' ', str(what))[:150]))
        print('         %s' % str(url_ or '')[:110])
    cx.close()

print('\nИТОГ ' + json.dumps({'смотрела': 'api.hh.ru, блок hh_vacancy_scan, сигналы hh'},
                             ensure_ascii=False))
