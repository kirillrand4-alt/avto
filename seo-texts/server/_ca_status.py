# -*- coding: utf-8 -*-
"""Статус всех процессов ЦА O2/N2 одной командой (для проверок раз в полчаса). Только чтение."""
import glob, json, os, subprocess
П = r'C:\sender\server\ca'
DIR = r'C:\sender\server'
print('===ИТОГ===')
r = subprocess.run(['powershell', '-NoProfile', '-Command',
                    '(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average; '
                    '$o=Get-CimInstance Win32_OperatingSystem; [math]::Round(100-100*$o.FreePhysicalMemory/$o.TotalVisibleMemorySize)'],
                   capture_output=True, text=True, timeout=120)
print('ЦП %, память %:', r.stdout.split())
for имя in ('ca-konveyer-obertka.json', 'ca-okved-dobor-progress.json', 'ca-rynok-15-progress.json', 'ca-signaly-progress.json', 'ca-gaz-zakupki-progress.json'):
    п = os.path.join(П, имя)
    print(имя, open(п, encoding='utf-8', errors='replace').read()[:400] if os.path.exists(п) else 'нет')
print('замки', [os.path.basename(x) for x in glob.glob(os.path.join(П, '*.lock'))])
п = os.path.join(DIR, 'ca-konveyer.json')
if os.path.exists(п):
    o = json.load(open(п, encoding='utf-8'))
    print('конвейер', {k: v for k, v in o.items() if k != 'шаги'})
    for k, v in (o.get('шаги') or {}).items():
        print('  ', k, v.get('старт'), v.get('конец', 'идёт'), v.get('код', ''), (v.get('хвост') or '')[-150:].replace('\n', ' | '))
for шаблон in (os.path.join(П, 'ca_spisok_*.log'), os.path.join(DIR, 'konveyer_ca_*.log')):
    for л in sorted(glob.glob(шаблон), key=os.path.getmtime)[-2:]:
        print(os.path.basename(л), '…', open(л, encoding='utf-8', errors='replace').read()[-300:].replace('\n', ' | '))
print('etp.env', 'есть' if os.path.exists(os.path.join(П, 'etp.env')) else 'нет')
for ф in ('ca-kontakty.jsonl',):
    п = os.path.join(DIR, ф)
    if os.path.exists(п):
        print(ф, 'строк', sum(1 for _ in open(п, encoding='utf-8', errors='replace')))
