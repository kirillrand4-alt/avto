# -*- coding: utf-8 -*-
r"""Общая проверка: зенка, разбор, поиск сайтов, диск, память, холды."""
import json
import os
import subprocess
import sys
import time
import urllib.request

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
os.chdir(DIR)
try:
    import poisk_saytov as PS  # noqa: F401  (поднимает ключи из runner-secrets)
except Exception:  # noqa: BLE001
    pass

ZENNO = r'C:\seostat\drop\zenno'
KESH = r'C:\seostat\drop\pagecache'
итог = {}


def строк(п):
    if not os.path.exists(п):
        return 0
    with open(п, encoding='utf-8-sig', errors='replace') as f:
        return sum(1 for s in f if s.strip())


def сколько(п, свежее_мин=None):
    порог = time.time() - (свежее_мин or 0) * 60
    n = 0
    try:
        with os.scandir(п) as it:
            for e in it:
                if not e.is_file():
                    continue
                if свежее_мин is None:
                    n += 1
                else:
                    try:
                        if e.stat().st_mtime >= порог:
                            n += 1
                    except OSError:
                        pass
    except OSError:
        return -1
    return n


итог['зенка'] = {
    'очередь': строк(os.path.join(ZENNO, 'ochered.txt')),
    'gotovo_ждёт_разбора': сколько(os.path.join(ZENNO, 'gotovo')),
    'кэш_карточек': сколько(KESH),
    'кэш_за_30мин': сколько(KESH, 30),
}
д = os.path.join(ZENNO, 'demon.out')
if os.path.exists(д):
    хв = [s for s in open(д, encoding='utf-8', errors='replace')][-2:]
    итог['зенка']['последний_круг'] = [s.strip()[:220] for s in хв]

лог = r'C:\sender\poisk_saytov.out'
if os.path.exists(лог):
    пачки = [s.strip() for s in open(лог, encoding='utf-8', errors='replace')
             if s.strip().startswith('{"взято"')]
    итог['поиск'] = {'пачек_всего': len(пачки), 'последние': пачки[-3:]}
try:
    u, k = os.environ.get('XMLRIVER_USER', ''), os.environ.get('XMLRIVER_KEY', '')
    итог['баланс_xmlriver'] = urllib.request.urlopen(
        'http://xmlriver.com/api/get_balance/?user=%s&key=%s' % (u, k),
        timeout=25).read().decode('utf-8', 'replace').strip()[:20]
except Exception as e:  # noqa: BLE001
    итог['баланс_сбой'] = str(e)[:80]

итог['холды'] = {и: os.path.exists(os.path.join(DIR, и))
                 for и in ('HOLD-POISK.flag', 'HOLD-FAKTY.flag')}
try:
    import storozh as S
    ж = S._живые()
    итог['процессы'] = {и: bool(S._крутится(ж, и))
                        for и in ('zenno_most.py', 'poisk_saytov.py',
                                  'fakty_cikl.py', 'enrich_contacts.py')}
except Exception as e:  # noqa: BLE001
    итог['процессы'] = str(e)[:90]

try:
    out = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "(Get-CimInstance Win32_Processor|Measure-Object LoadPercentage -Average).Average;"
         "(Get-CimInstance Win32_OperatingSystem|%{[int]($_.FreePhysicalMemory/1024)});"
         "(Get-PSDrive C).Free/1GB"],
        capture_output=True, text=True, timeout=90)
    ч = [x.strip() for x in out.stdout.split() if x.strip()]
    итог['машина'] = {'цп_проц': ч[0] if ч else '?',
                      'память_свободно_мб': ч[1] if len(ч) > 1 else '?',
                      'диск_свободно_гб': ч[2][:6] if len(ч) > 2 else '?'}
except Exception as e:  # noqa: BLE001
    итог['машина'] = str(e)[:90]

print(json.dumps(итог, ensure_ascii=False, indent=1))
