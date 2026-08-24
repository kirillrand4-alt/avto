# -*- coding: utf-8 -*-
r"""Остановить всё, что ходит к провайдеру. Владелец 24.08: «останови».

Три потребителя, и глушить их надо по-разному:
  * fakty_cikl — вечный цикл паспортов, зовёт луну и хайку напрямую;
  * enrich_contacts — батчи обогащения (extract_model=gpt-5.6-luna), их шлют
    мост Зенки в доработке и очередь `enrich_panel`; сам мост при этом
    провайдера не трогает и остаётся жить, он просто возит страницы;
  * poisk_saytov — платный XMLRiver плюс проверка через провайдера.

Флаги ставим ПЕРВЫМИ: сторож смотрит на них каждый круг, и без них он поднял
бы погашенное обратно через минуту. Мост тоже читает HOLD-FAKTY.flag и после
него доработку не запускает.

ГРАБЛИ (24.08, потратил на них полчаса): по имени `enrich_contacts.py` ходит
не только обогащение. Тем же скриптом раннер исполняет задачу op='panel_py' —
это механизм «выполни мой скрипт на сервере» (`run_script_on_server.py`).
Поэтому убитый по маске enrich_contacts тут же «воскресает» — это не провайдер
ожил, это следующий мой же диагностический запуск. Различить по командной
строке нельзя: аргументы уходят скрипту через stdin, в cmdline всегда голое
`enrich_contacts.py`. Отсюда правило: по умолчанию гасим только fakty_cikl и
poisk_saytov, а enrich_contacts — лишь по явному `--i-enrich`, понимая, что
заодно оборвутся текущие серверные запуски скриптов.

Снять холд: удалить оба флага в C:\sender\server.
"""
import json
import os
import subprocess
import sys
import time

DIR = r'C:\sender\server'
МАСКА = 'fakty_cikl|poisk_saytov'
if '--i-enrich' in sys.argv:
    МАСКА += '|enrich_contacts'

d = {'флаги': {}, 'маска': МАСКА}
for флаг, зачем in (('HOLD-FAKTY.flag', 'паспорта и разбор моста'),
                    ('HOLD-POISK.flag', 'поиск сайтов: xmlriver + провайдер')):
    п = os.path.join(DIR, флаг)
    if not os.path.exists(п):
        with open(п, 'w', encoding='utf-8') as f:
            f.write('поставлен по команде владельца 24.08 «останови то что '
                    'запрашивает провайдера»: %s\n%s\n'
                    % (зачем, time.strftime('%Y-%m-%d %H:%M:%S')))
            f.flush()
            os.fsync(f.fileno())
        d['флаги'][флаг] = 'поставлен'
    else:
        d['флаги'][флаг] = 'уже стоял'

# гасим сами процессы
out = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -match '" + МАСКА + "'} "
     "| %{ '{0}|{1}' -f $_.ProcessId, ($_.CommandLine -replace '.*\\\\','') ; "
     'Stop-Process -Id $_.ProcessId -Force }'],
    capture_output=True, text=True, timeout=180)
d['погашено'] = [s.strip()[:70] for s in (out.stdout or '').splitlines() if s.strip()]
time.sleep(5)
пров = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Where-Object {$_.CommandLine -match '" + МАСКА + "'} "
     '| %{ $_.ProcessId }'], capture_output=True, text=True, timeout=120)
d['осталось_живых'] = [s.strip() for s in (пров.stdout or '').split() if s.strip()]
живые = subprocess.run(
    ['powershell', '-NoProfile', '-Command',
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "%{ $_.CommandLine } | Select-String -Pattern 'zenno_most|serve-api|storozh' "
     '| %{ $_.ToString().Trim() }'], capture_output=True, text=True, timeout=120)
d['продолжают_работать'] = [s.strip()[-60:] for s in
                            (живые.stdout or '').splitlines() if s.strip()][:6]
print(json.dumps(d, ensure_ascii=False, indent=1))
