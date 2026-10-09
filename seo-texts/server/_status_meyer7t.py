# -*- coding: utf-8 -*-
"""Статус тестовой партии Meyer (набор meyer7t): строки журналов, шаги конвейера, хвосты логов набора, живые процессы
конвейера (любого набора — чтобы стоп не задел чужое), баланс xmlriver."""
import glob
import json
import os
import subprocess
import urllib.request

DIR = r'C:\sender\server'
НАБОР = 'meyer7t'
o = {}
for х in ('-serp.jsonl', '-razbor.jsonl', '-spisok.json', '-sayty-dobor.jsonl', '-kontakty.jsonl', '-dop.jsonl',
          '-pasport.jsonl', '-audit.jsonl', '-audit2.jsonl', '-sayt-proverka.jsonl', '-oprov.jsonl', '-glubokiy.jsonl',
          '-glubokiy2.jsonl', '-reestr.json', '-zenka.json'):
    ф = os.path.join(DIR, НАБОР + х)
    if os.path.exists(ф):
        o[х] = sum(1 for _ in open(ф, encoding='utf-8', errors='replace'))
ф = os.path.join(DIR, НАБОР + '-serp.jsonl')
if os.path.exists(ф):
    ош = всего = 0
    for s in open(ф, encoding='utf-8', errors='replace'):
        всего += 1
        ош += '"итог": "ошибка"' in s
    o['serp_ошибок'] = '%d из %d' % (ош, всего)
ф = os.path.join(DIR, НАБОР + '-konveyer.json')
if os.path.exists(ф):
    к = json.load(open(ф, encoding='utf-8'))
    o['конвейер'] = {ш: '%s→%s код %s' % (v.get('старт', ''), v.get('конец', ''), v.get('код', '')) for ш, v in к.get('шаги', {}).items()}
    o['конвейер_ждёт'] = к.get('ждём', '')
    o['конвейер_стоп'] = к.get('стоп', '') or к.get('конец', '')
логи = sorted(glob.glob(os.path.join(DIR, '*%s*.log' % НАБОР)), key=os.path.getmtime)[-3:]
for л in логи:
    with open(л, encoding='utf-8', errors='replace') as f:
        o['лог ' + os.path.basename(л)] = f.read()[-700:]
try:
    r = subprocess.run(['powershell', '-NoProfile', '-Command',
                        "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and "
                        "($_.CommandLine -like '*pilot_*' -or $_.CommandLine -like '*kc_*' -or $_.CommandLine -like '*poisk_*') "
                        "-and $_.CommandLine -notlike '*_status_*' } | ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }"],
                       capture_output=True, text=True, timeout=60)
    o['процессы'] = [x[-90:] for x in r.stdout.splitlines() if x.strip()]
except Exception as e:  # noqa: BLE001
    o['процессы'] = repr(e)
try:
    оп = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    o['xmlriver'] = оп.open('http://xmlriver.com/api/get_balance/?user=%s&key=%s' % (
        os.environ.get('XMLRIVER_USER', ''), os.environ.get('XMLRIVER_KEY', '')), timeout=30).read(100).decode()
except Exception as e:  # noqa: BLE001
    o['xmlriver'] = repr(e)[:100]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
