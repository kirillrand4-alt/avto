# -*- coding: utf-8 -*-
"""Разведка №0.1: короткие списки под два источника + сохранение на сервер.

A: под патенты — производственный профиль (завод/НПО/НИИ/машиностроение/химия).
B: под раскрытие — только АО/ПАО/ОАО, желательно с сайтом.

Пишем оба списка в C:\\sender\\_ops\\pat_targets.json (серверный durable-файл),
чтобы следующие проходы брали ровно тех же и были резюмируемы.
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_db as EDB          # noqa: E402
import enrich_contacts as EC     # noqa: E402

db = EDB.EnrichDB()
e = db.cx

БАЗА = json.load(open(r'C:\sender\_ops\sales_base.json', encoding='utf-8'))
инны, было = [], set()
for строки in БАЗА.values():
    for x in строки:
        i = str(x.get('inn') or '').strip()
        if i and i not in было:
            было.add(i)
            инны.append((i, str(x.get('name') or '')))

_АО = re.compile(r'(^|[^А-ЯЁа-яё])(АО|ПАО|ОАО|ЗАО)([^А-ЯЁа-яё]|$)|'
                 r'АКЦИОНЕРНОЕ\s+ОБЩЕСТВО', re.I)
_ПРОМ = re.compile(
    r'завод|НПО|НПП|НИИ|КБ\b|машиностроит|механич|металлург|комбинат|'
    r'приборостро|аппарат|турбин|котел|котёл|электро|станко|агрегат|'
    r'хими|нефт|газ|цемент|стекл|бумаг|целлюлоз|шин\b|инструмент|'
    r'производствен|объединен|энерг|горн|рудн|обогатит', re.I)

ао, пром = [], []
for i, n in инны:
    r = e.execute('SELECT name, site, okved, is_competitor FROM companies '
                  'WHERE inn=?', (i,)).fetchone()
    имя = (r[0] if r and r[0] else n) or ''
    сайт = (r[1] if r else '') or ''
    бренд = EC.бренд_компании(имя, сайт)
    зап = {'inn': i, 'name': имя, 'brand': бренд, 'site': сайт}
    if _АО.search(имя):
        ао.append(зап)
    if _ПРОМ.search(имя) or _ПРОМ.search(бренд):
        пром.append(зап)

# для патентов: производственные, сперва те, у кого внятный бренд (не обрезок)
def внятный(x):
    b = x['brand']
    return (len(b) >= 4 and not b.endswith('-') and
            not re.search(r'(ОБЩЕСТВ|ОГРАНИЧЕН|ОТВЕТСТВЕН)', b, re.I))


патенты_цели = [x for x in пром if внятный(x)][:60]
раскрытие_цели = [x for x in ао if внятный(x)][:60]

json.dump({'патенты': патенты_цели, 'раскрытие': раскрытие_цели},
          open(r'C:\sender\_ops\pat_targets.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)

print('--- ПОД ПАТЕНТЫ (производственные), первые 30 ---')
for x in патенты_цели[:30]:
    print(x['inn'], '|', x['brand'][:38], '|', x['site'][:28], '|', x['name'][:52])
print('--- ПОД РАСКРЫТИЕ (АО/ПАО), первые 30 ---')
for x in раскрытие_цели[:30]:
    print(x['inn'], '|', x['brand'][:38], '|', x['site'][:28], '|', x['name'][:52])
print('ИТОГ пром=%d ао=%d записано в pat_targets.json' %
      (len(патенты_цели), len(раскрытие_цели)))
