# -*- coding: utf-8 -*-
r"""Цепочка по базе RSS доноров: сперва автодискавери лент, потом сбор по ним.

Почему отдельно. В прогоне 16.09 участвовал коллектор `regional` — а он читает
каталог news-sources.json с дропа, и там 14 федеральных лент. База RSS доноров
(таблица donors в enrich.db: 799 доменов, у 115 найдена живая лента) читается
ДРУГИМ коллектором — `rss`, и его в списке не было.

Шаг 1: rss_discover по донорам без отметки (539 из 799 вообще не проверялись).
Шаг 2: сбор по всем живым лентам.

Оба шага пишут в news_stream.jsonl с fsync, поэтому занятая база результат не
съест: недостающее донесёт dobor_signalov_iz_potoka.py.
"""
import json
import os
import subprocess
import sys
import time

DIR = r'C:\sender\server'
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python):
    python = sys.executable
МЕТКА = time.strftime('%d%m-%H%M')


def шаг(имя, args, tmo):
    вход = os.path.join(DIR, 'rss_args_%s_%s.json' % (имя, МЕТКА))
    лог = os.path.join(DIR, 'rss_%s_%s.log' % (имя, МЕТКА))
    with open(вход, 'w', encoding='utf-8') as f:
        json.dump(args, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    with open(вход, 'rb') as fi, open(лог, 'wb') as fo:
        p = subprocess.run([python, '-u', 'news_scan.py'], cwd=DIR, stdin=fi,
                           stdout=fo, stderr=subprocess.STDOUT, timeout=tmo)
    with open(лог, encoding='utf-8', errors='replace') as f:
        текст = f.read()
    return {'rc': p.returncode, 'лог': os.path.basename(лог),
            'хвост': текст[-700:]}


итог = {'начало': time.strftime('%H:%M:%S')}
try:
    итог['дискавери'] = шаг('discover', {'rss_discover': 'db', 'limit': 600}, 3000)
except Exception as e:  # noqa: BLE001
    итог['дискавери'] = 'ОШИБКА: %r' % (e,)

try:
    итог['сбор'] = шаг('sbor', {
        'collectors': ['rss'],
        'days': 45,
        'max_items': 8,
        'rss_cap_feeds': 300,
        'enrich': True,
        'enrich_max': 0,
        'icp_only': False,
        'write_db': True,
        'provider_workers': 12,
    }, 12000)
except Exception as e:  # noqa: BLE001
    итог['сбор'] = 'ОШИБКА: %r' % (e,)

итог['конец'] = time.strftime('%H:%M:%S')
with open(os.path.join(DIR, 'rss_cepochka_%s.itog.json' % МЕТКА), 'w', encoding='utf-8') as f:
    json.dump(итог, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps(итог, ensure_ascii=False, indent=1))
