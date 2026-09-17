# -*- coding: utf-8 -*-
"""Идёт ли сбор и КОРРЕКТЕН ли он: сверяем ИНН с названием, даты, дубли."""
import io
import json
import os
import re
import subprocess
import time
import urllib.request

DIR = r'C:\sender\server'
o = {'сейчас': time.strftime('%H:%M:%S')}

# 1. Процессы и лог.
r = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -like '*news_scan*'} | ForEach-Object { "
     "$pr = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue; "
     "[pscustomobject]@{pid=$_.ProcessId; cpu=[math]::Round($pr.CPU,0)} } | ConvertTo-Json -Compress"],
    capture_output=True, text=True, timeout=90)
o['процессы'] = (r.stdout or '').strip()[:200]
логи = sorted([p for p in os.listdir(DIR) if p.startswith('xmlriver_scan_')])
if логи:
    п = os.path.join(DIR, логи[-1])
    o['лог'] = {'файл': логи[-1], 'байт': os.path.getsize(п),
                'изменён': time.strftime('%H:%M:%S', time.localtime(os.stat(п).st_mtime))}
    if os.path.getsize(п):
        with open(п, encoding='utf-8', errors='replace') as f:
            o['лог']['хвост'] = f.read()[-350:]

# 2. Собираем сегодняшние события xmlriver из потока.
события = []
with io.open(os.path.join(DIR, 'news_stream.jsonl'), encoding='utf-8', errors='replace') as f:
    n = 0
    for s in f:
        n += 1
        if n <= 5270 or 'xmlriver' not in s[:400]:
            continue
        try:
            события.append(json.loads(s))
        except Exception:
            pass
o['всего_событий_xmlriver'] = len(события)
o['строк_в_потоке'] = n

# 3. Корректность дат: попадают ли в окно 45 дней.
сегодня = time.time()
в_окне = вне = без_даты = 0
for d in события:
    p = str(d.get('published') or '')
    м = re.search(r'(20\d\d)-(\d\d)-(\d\d)', p)
    if not м:
        без_даты += 1
        continue
    try:
        t = time.mktime(time.strptime('%s-%s-%s' % м.groups(), '%Y-%m-%d'))
    except Exception:
        без_даты += 1
        continue
    if (сегодня - t) / 86400 <= 50:
        в_окне += 1
    else:
        вне += 1
o['даты'] = {'в_окне_45_дней': в_окне, 'старее': вне, 'без_даты': без_даты}

# 4. Дубли: сколько событий указывают на ссылку, уже лежащую в signals.
import sqlite3
c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=30)
ссылки = {u for (u,) in c.execute("select coalesce(source_url,'') from signals")}
дубли = sum(1 for d in события if (d.get('source_url') or '') in ссылки)
o['дубли_по_ссылке'] = дубли
o['сигналов_в_базе'] = c.execute('select count(*) from signals').fetchone()[0]
c.close()

# 5. Главное: верен ли ИНН. Берём 8 событий с ИНН и спрашиваем dadata по ИНН,
#    сверяя вернувшееся название с тем, что записал классификатор.
ТОК = os.environ.get('DADATA_TOKEN', '')
проверка = []
с_инн = [d for d in события if str(d.get('inn') or '').strip()]
for d in с_инн[:8]:
    inn = str(d['inn'])
    имя_наше = (d.get('company') or '')
    факт = ''
    try:
        req = urllib.request.Request(
            'https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party',
            data=json.dumps({'query': inn}).encode(),
            headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                     'Authorization': 'Token ' + ТОК})
        with urllib.request.urlopen(req, timeout=25) as rr:
            d2 = json.loads(rr.read())
        s = (d2.get('suggestions') or [{}])[0]
        факт = (s.get('value') or '')
        статус = ((s.get('data') or {}).get('state') or {}).get('status', '')
    except Exception as e:
        факт, статус = 'ошибка: %r' % (e,), ''
    ядро = re.sub(r'[«»"\'`]', '', имя_наше.lower())
    ядро = re.sub(r'\b(ооо|оао|зао|пао|ао|нао|группа|компания|гк)\b', '', ядро).strip()
    совпало = bool(ядро) and ядро.split()[0][:6] in факт.lower() if ядро else False
    проверка.append({'инн': inn, 'у_нас': имя_наше[:40], 'в_егрюл': факт[:60],
                     'статус': статус, 'сошлось': совпало})
o['сошлось_из'] = '%d из %d' % (sum(1 for x in проверка if x['сошлось']), len(проверка))
o['несошедшиеся'] = [x for x in проверка if not x['сошлось']][:3]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5200])
