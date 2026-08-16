# -*- coding: utf-8 -*-
r"""Забрать файл С СЕРВЕРА в песочницу кусками через panel_py.

Обратной операции к panel_file_put у нас нет, а вывод скрипта раннер обрезает до
6 КБ хвоста — отчёт на 50 компаний так не заберёшь. Дроп бы решил, но сервер до
него не ходит («Connection not allowed by ruleset»), поэтому читаем сами: серверный
скрипт печатает base64-кусок по смещению, здесь куски склеиваются.

    python zabrat_fayl.py "C:\sender\server\otchet.html" otchet.html
"""
import base64
import gzip
import json
import os
import subprocess
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
КУСОК = 5600                       # base64-кусок, чтобы влезал в 6 КБ хвоста stdout
ЧИТАЛКА = r'C:\sender\server\_kusok_fayla.py'
# Файл забираем СЖАТЫМ. Отчёт на 50 компаний — 125 КБ, а в один заход влезает
# ~4 КБ (раннер отдаёт 6 КБ хвоста stdout): 55 рейсов по 10-20 секунд каждый.
# Тот же отчёт в gzip — 20 КБ, это девять рейсов.
ИСХОДНИК = '''# -*- coding: utf-8 -*-
import base64, gzip, os, shutil, sys
p, off, n = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
g = p + '.vygruzka.gz'
if off == 0 or not os.path.exists(g):
    with open(p, 'rb') as src, gzip.open(g, 'wb', compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)
with open(g, 'rb') as f:
    f.seek(off)
    b = f.read(n)
sys.stdout.write('<<%d>>' % len(b) + base64.b64encode(b).decode())
'''


def _op(payload, timeout=600):
    p = subprocess.run([sys.executable, 'run_on_server.py', 'enrich_contacts',
                        json.dumps(payload, ensure_ascii=False)],
                       cwd=DIR, capture_output=True, text=True, timeout=timeout)
    i = p.stdout.find('{')
    d = json.loads(p.stdout[i:]) if i >= 0 else {'raw': p.stdout[-300:]}
    return d.get('data') or d


def забрать(путь, куда):
    r = _op({'op': 'panel_file_put',
             'files': [{'b64': base64.b64encode(ИСХОДНИК.encode()).decode(),
                        'dest': ЧИТАЛКА}]})
    if not r.get('ok'):
        return {'не залилась читалка': r}
    сырое = b''
    смещение = 0
    while True:
        байт = int(КУСОК * 3 / 4)
        d = _op({'op': 'panel_py', 'script': ЧИТАЛКА,
                 'argv': [путь, str(смещение), str(байт)], 'timeout': 120})
        хвост = d.get('stdout_tail') or ''
        i = хвост.find('<<')
        j = хвост.find('>>')
        if i < 0 or j < 0:
            return {'сбой чтения': d}
        сколько = int(хвост[i + 2:j])
        сырое += base64.b64decode(хвост[j + 2:])
        смещение += сколько
        if сколько < байт:
            break
    данные = gzip.decompress(сырое)
    with open(куда, 'wb') as f:
        f.write(данные)
    return {'скачано_сжатым': len(сырое), 'развернулось_в': len(данные), 'файл': куда}


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    print(json.dumps(забрать(sys.argv[1], sys.argv[2]), ensure_ascii=False))
