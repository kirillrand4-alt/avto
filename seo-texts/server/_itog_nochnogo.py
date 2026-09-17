# -*- coding: utf-8 -*-
"""Чем кончился ночной прогон скана: лог, поток, сигналы, что в базе нового."""
import glob
import json
import os
import sqlite3
import time

DIR = r'C:\sender\server'
o = {'сейчас': time.strftime('%Y-%m-%d %H:%M:%S')}

for путь in sorted(glob.glob(os.path.join(DIR, 'news_scan_*.log')), key=os.path.getmtime)[-2:]:
    st = os.stat(путь)
    зап = {'байт': st.st_size,
           'изменён': time.strftime('%d.%m %H:%M', time.localtime(st.st_mtime))}
    if st.st_size:
        with open(путь, encoding='utf-8', errors='replace') as f:
            зап['хвост'] = f.read()[-1500:]
    o.setdefault('логи_скана', {})[os.path.basename(путь)] = зап

П = os.path.join(DIR, 'news_stream.jsonl')
o['поток_байт'] = os.path.getsize(П)
строк = 0
with open(П, encoding='utf-8', errors='replace') as f:
    for _ in f:
        строк += 1
o['строк_в_потоке'] = строк

c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=30)
o['сигналов'] = c.execute('select count(*) from signals').fetchone()[0]
o['сигналов_за_вчера'] = c.execute(
    "select count(*) from signals where updated_at like '2026-09-16%'").fetchone()[0]
o['сигналов_за_сегодня'] = c.execute(
    "select count(*) from signals where updated_at like '2026-09-17%'").fetchone()[0]
c.close()

отм = os.path.join(DIR, 'news_stream.dobor-otmetka.json')
o['отметка_добора'] = open(отм, encoding='utf-8').read()[:120] if os.path.exists(отм) else 'нет'
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
