# -*- coding: utf-8 -*-
r"""Погасить разбор с провайдером, перезапустить мост, посчитать прошедшее.

Разбор моста (dorabotka -> enrich_contacts, extract_model=gpt-5.6-luna) ходил
к провайдеру мимо холда владельца. Гейт добавлен в zenno_most.dorabotka, здесь
снимаем уже запущенный процесс и меряем, сколько вызовов успело пройти.
"""
import json
import os
import subprocess
import sys
import time

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
os.chdir(DIR)
ZENNO = r'C:\seostat\drop\zenno'
итог = {}


def погасить(маска):
    out = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
         "Where-Object {$_.CommandLine -like '*%s*'} | "
         "%%{ Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }" % маска],
        capture_output=True, text=True, timeout=90)
    return [x.strip() for x in out.stdout.split() if x.strip()]


# сколько вызовов провайдера прошло с момента холда (19.08 19:46)
п = os.path.join(DIR, 'zenno_razbor.jsonl')
счёт = {'provider': 0, 'regex': 0, 'provider-fail': 0, 'всего': 0}
if os.path.exists(п):
    with open(п, encoding='utf-8', errors='replace') as f:
        for s in f:
            try:
                d = json.loads(s)
            except Exception:  # noqa: BLE001
                continue
            счёт['всего'] += 1
            e = str(d.get('extract') or '')
            if e == 'provider':
                счёт['provider'] += 1
            elif 'provider-fail' in e:
                счёт['provider-fail'] += 1
            elif e:
                счёт['regex'] += 1
    счёт['журнал_с'] = time.strftime(
        '%Y-%m-%d %H:%M', time.localtime(os.path.getctime(п)))
итог['разбор_за_всё_время'] = счёт

итог['погашено_разбор'] = погасить('enrich_contacts.py')
итог['погашено_мост'] = погасить('zenno_most.py')
for н in ('razbor.pid',):
    p = os.path.join(ZENNO, н)
    if os.path.exists(p):
        os.remove(p)
        итог['снят_замок'] = н
time.sleep(4)
import storozh as S  # noqa: E402
итог['сторож'] = S.обход()
time.sleep(18)
ж = S._живые()
итог['крутится'] = {и: bool(S._крутится(ж, и)) for и in
                    ('zenno_most.py', 'enrich_contacts.py', 'poisk_saytov.py')}
print(json.dumps(итог, ensure_ascii=False, indent=1))
