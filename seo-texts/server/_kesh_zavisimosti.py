# -*- coding: utf-8 -*-
"""Кто читает кэш страниц и сколько весил бы «текст без HTML».

Три вопроса разом:
  1) сироты — это найденные вне базы (их контакты уже сняты) или мусор?
  2) читает ли кэш ПАНЕЛЬ при генерации письма (тогда удаление ломает письма);
  3) во сколько раз легче тот же кэш, если хранить текст, а не разметку.
"""
import gzip
import io
import json
import os
import random
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
итог = {}

# 1. сироты
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
в_компаниях = {str(r[0]) for r in c.execute('select inn from companies')}
вне_базы = set()
for т in ('vne_bazy', 'najdeny_vne_bazy'):
    try:
        вне_базы |= {str(r[0]) for r in c.execute('select inn from %s' % т)}
    except Exception:  # noqa: BLE001
        pass
готовые = {str(r[0]) for r in c.execute(
    "select inn from site_facts where coalesce(facts_json,'')<>'' "
    'and coalesce(format,0)>=2')}
c.close()
файлы = [f for f in os.listdir(KESH) if f.endswith('.json.gz')]
сироты = [f[:-8] for f in файлы if f[:-8] not in в_компаниях]
итог['сирот'] = len(сироты)
итог['сирот_из_них_вне_базы'] = sum(1 for i in сироты if i in вне_базы)

# 2. читает ли панель
места = []
for корень in (r'C:\sender\sender',):
    for d, _, fs in os.walk(корень):
        if '__pycache__' in d:
            continue
        for f in fs:
            if not f.endswith('.py'):
                continue
            try:
                t = io.open(os.path.join(d, f), encoding='utf-8', errors='replace').read()
            except Exception:  # noqa: BLE001
                continue
            if re.search(r'pagecache|PAGECACHE|json\.gz', t):
                места.append(f)
итог['панель_читает_кэш'] = sorted(set(места)) or 'нет — панель кэш не трогает'

# 3. текст вместо HTML на выборке готовых
проба = random.Random(17).sample([f for f in файлы if f[:-8] in готовые],
                                 min(40, len(файлы)))
было = стало = 0
for имя in проба:
    п = os.path.join(KESH, имя)
    было += os.path.getsize(п)
    try:
        d = json.loads(gzip.open(п, 'rb').read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        continue
    страницы = []
    for pg in (d.get('pages') or []):
        h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', pg.get('html') or '',
                   flags=re.S | re.I)
        страницы.append({'url': pg.get('url') or '',
                         'text': re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h)).strip()})
    стало += len(gzip.compress(json.dumps(
        {'pages': страницы}, ensure_ascii=False).encode('utf-8'), 6))
итог['проба_файлов'] = len(проба)
итог['проба_было_МБ'] = round(было / 2**20, 1)
итог['проба_стало_текстом_МБ'] = round(стало / 2**20, 1)
итог['во_сколько_легче'] = round(было / стало, 1) if стало else None
print(json.dumps(итог, ensure_ascii=False, indent=1))
