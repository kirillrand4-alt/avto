# -*- coding: utf-8 -*-
r"""Ход поиска сайтов: последние пачки, баланс, свежие находки."""
import json
import os
import sys
import time
import urllib.request

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
os.chdir(DIR)
try:
    import poisk_saytov as PS  # noqa: F401  (нужен только ради подъёма ключей)
except Exception:  # noqa: BLE001
    pass

if len(sys.argv) > 1 and sys.argv[1].isdigit():
    time.sleep(int(sys.argv[1]))

итог = {}
лог = r'C:\sender\poisk_saytov.out'
if os.path.exists(лог):
    строки = [s.strip() for s in open(лог, encoding='utf-8', errors='replace')
              if s.strip().startswith('{')]
    итог['последние_пачки'] = строки[-4:]

j = r'C:\sender\poisk_saytov.jsonl'
свежие, порог = [], time.time() - 3600
if os.path.exists(j):
    разм = os.path.getsize(j)
    with open(j, encoding='utf-8', errors='replace') as f:
        f.seek(max(0, разм - 400000))
        f.readline()
        хвост = [s for s in f]
    нашли = [json.loads(s) for s in хвост[-1500:]
             if s.strip().startswith('{')]
    свежие = [{'инн': d.get('inn'), 'имя': (d.get('name') or '')[:38],
               'сайт': d.get('site'), 'вердикт': d.get('verdikt') or d.get('src')}
              for d in нашли if d.get('site')][-8:]
    итог['последних_строк_в_логе'] = len(хвост)
итог['свежие_находки'] = свежие

u, k = os.environ.get('XMLRIVER_USER', ''), os.environ.get('XMLRIVER_KEY', '')
if u and k:
    try:
        итог['баланс'] = urllib.request.urlopen(
            'http://xmlriver.com/api/get_balance/?user=%s&key=%s' % (u, k),
            timeout=25).read().decode('utf-8', 'replace').strip()[:40]
    except Exception as e:  # noqa: BLE001
        итог['баланс_сбой'] = str(e)[:100]

try:
    import storozh as S
    итог['крутится'] = bool(S._крутится(S._живые(), 'poisk_saytov.py'))
except Exception as e:  # noqa: BLE001
    итог['крутится_сбой'] = str(e)[:80]
print(json.dumps(итог, ensure_ascii=False, indent=1))
