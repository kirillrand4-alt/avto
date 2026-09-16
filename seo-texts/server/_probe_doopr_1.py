# -*- coding: utf-8 -*-
"""Проба 1 к задаче «доопределение компании»: что реально лежит в signals и в
news_stream.jsonl на сервере. ТОЛЬКО ЧТЕНИЕ (mode=ro), ничего не пишет, сети не трогает.

Считаем:
  * сколько событий, у скольких заполнен region/ts, какие форматы ts;
  * сколько текстов упоминают ОЭЗ/ТОР/резидент (потолок пути 1);
  * сколько объектов встречается в НЕСКОЛЬКИХ новостях (потолок пути 5);
  * где лежит news_stream.jsonl и сколько там записей без company / без inn.
ВАЖНО: stdout раннера режется СВЕРХУ → итог печатаем ПОСЛЕДНИМ.
"""
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict

DB = r'file:C:\sender\enrich.db?mode=ro'
cx = sqlite3.connect(DB, uri=True)
cx.row_factory = sqlite3.Row

cols = [r[1] for r in cx.execute('PRAGMA table_info(signals)')]
print('signals cols:', cols)

rows = [dict(r) for r in cx.execute('SELECT * FROM signals')]
print('signals rows:', len(rows))

# ---- образцы текстов (идут первыми, их и обрежет, если что)
for r in rows[:5]:
    print('SAMPLE|', r.get('source'), '|', (r.get('ts') or '')[:25], '|',
          (r.get('what') or '')[:160].replace('\n', ' '))

# ---- форматы ts
def ts_kind(t):
    t = (t or '').strip()
    if not t:
        return 'пусто'
    if re.match(r'^\d{4}-\d{2}-\d{2}', t):
        return 'ISO'
    if re.match(r'^[A-Za-z]{3},', t):
        return 'RFC822'
    if re.match(r'^\d{4}-\d{2}$', t):
        return 'YYYY-MM'
    return 'иное'


ts_c = Counter(ts_kind(r.get('ts')) for r in rows)

# ---- упоминания ОЭЗ/ТОР/резидентства и инвестпорталов
PAT = {
    'ОЭЗ/ТОР/резидент': r'\bОЭЗ\b|\bТОР\b|\bТОСЭР\b|особой экономической|территори\w+ опережающ|резидент',
    'индустриальный парк': r'индустриальн\w+ парк|технопарк|промышленн\w+ парк|промпарк',
    'ФРП/займ': r'\bФРП\b|фонд\w* развития промышленности|займ',
    'СПИК/СЗПК': r'\bСПИК\b|\bСЗПК\b|специальн\w+ инвестиционн',
    'экспертиза/проект': r'экспертиз\w+|проектн\w+ документац|ЕГРЗ',
    'инвестсоглашение': r'соглашени\w+ о (?:реализации|строительстве)|инвестсоглашени|подписал\w* соглашени',
}
pat_c = Counter()
for r in rows:
    txt = ((r.get('what') or '') + ' ' + (r.get('event_type') or ''))
    for k, p in PAT.items():
        if re.search(p, txt, re.I):
            pat_c[k] += 1

# ---- ключ объекта: тип объекта + предметные слова
OBJ = ('завод', 'фабрик', 'комбинат', 'цех', 'лини', 'комплекс', 'элеватор', 'терминал',
       'рудник', 'карьер', 'птицефабрик', 'ферм', 'теплиц', 'склад', 'производств')
STOP = set('''и в на по для с из от до за при о об а но что как это тот эта этот там где
когда уже ещё еще был была было были будет будут может можно новый новая новое новые
млн млрд руб рублей года году год рф россии компания предприятие'''.split())


def toks(s):
    return [t for t in re.sub(r'[^а-яёa-z0-9 ]', ' ', (s or '').lower()).split()
            if len(t) >= 4 and t not in STOP]


def obj_key(row):
    """Грубый ключ объекта: регион-подсказка из текста + тип объекта + 2 редких слова."""
    t = (row.get('what') or '')
    tk = toks(t)
    o = [w for w in tk if any(w.startswith(p[:5]) for p in OBJ)]
    rare = [w for w in tk if len(w) >= 7 and w not in o][:3]
    if not o or not rare:
        return None
    return (o[0][:6], tuple(sorted(w[:7] for w in rare)))


by_key = defaultdict(list)
for r in rows:
    k = obj_key(r)
    if k:
        by_key[k].append(r)

multi = {k: v for k, v in by_key.items() if len(v) >= 2}
multi_diff_url = {k: v for k, v in multi.items()
                  if len({(x.get('source_url') or '')[:80] for x in v}) >= 2}
multi_same_inn = {k: v for k, v in multi_diff_url.items()
                  if len({x.get('inn') for x in v}) == 1}
multi_diff_inn = {k: v for k, v in multi_diff_url.items()
                  if len({x.get('inn') for x in v}) > 1}

# сколько ИНН встречается больше одного раза (объект ведётся во времени)
inn_c = Counter(r.get('inn') for r in rows)
inn_multi = sum(1 for _i, n in inn_c.items() if n >= 2)

# ---- news_stream.jsonl: где он и что в нём
cand = [r'C:\sender\server\news_stream.jsonl', r'C:\sender\news_stream.jsonl',
        r'C:\sender\sender\news_stream.jsonl', r'C:\seostat\news_stream.jsonl']
js_path, js_stat = '', {}
for p in cand:
    if os.path.isfile(p):
        js_path = p
        break
if js_path:
    n = no_comp = no_inn = 0
    for line in open(js_path, encoding='utf-8', errors='replace'):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        n += 1
        if not (d.get('company') or '').strip():
            no_comp += 1
        if not (d.get('inn') or ''):
            no_inn += 1
    js_stat = {'записей': n, 'без company': no_comp, 'без inn': no_inn,
               'мб': round(os.path.getsize(js_path) / 1e6, 1)}

# ---- региональное покрытие компаний (нужно для защиты от тёзок)
comp_reg = cx.execute(
    'SELECT COUNT(*), SUM(CASE WHEN region IS NOT NULL AND region<>"" THEN 1 ELSE 0 END) '
    'FROM companies WHERE inn IN (SELECT DISTINCT inn FROM signals)').fetchone()

print()
print('==================== ИТОГ (главное) ====================')
print('событий в signals:', len(rows), '| разных ИНН:', len(inn_c),
      '| ИНН с >=2 событиями:', inn_multi)
print('форматы ts:', dict(ts_c))
print('упоминания по темам:', dict(pat_c))
print('ключ объекта построился у:', sum(len(v) for v in by_key.values()), 'событий,',
      'разных ключей:', len(by_key))
print('ключей с >=2 событиями:', len(multi),
      '| из них с РАЗНЫМИ ссылками:', len(multi_diff_url))
print('  из них один и тот же ИНН (честная склейка):', len(multi_same_inn),
      '| РАЗНЫЕ ИНН (ложная склейка ключа):', len(multi_diff_inn))
print('событий, попавших в кластер >=2 с разными ссылками:',
      sum(len(v) for v in multi_diff_url.values()))
print('компаний с сигналами / из них с регионом:', tuple(comp_reg))
print('news_stream.jsonl:', js_path or 'НЕ НАЙДЕН', js_stat)
for k, v in list(multi_same_inn.items())[:4]:
    print('  КЛАСТЕР-ОК', k, '->', [(x.get('inn'), (x.get('what') or '')[:60]) for x in v][:3])
for k, v in list(multi_diff_inn.items())[:4]:
    print('  КЛАСТЕР-ЛОЖНЫЙ', k, '->', [(x.get('inn'), (x.get('what') or '')[:60]) for x in v][:3])
