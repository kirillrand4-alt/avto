# -*- coding: utf-8 -*-
r"""Короткая сводка: очередь зенки, ход обхода, загрузка машины."""
import json
import os
import subprocess
import time

ZENNO = r'C:\seostat\drop\zenno'
KESH = r'C:\seostat\drop\pagecache'


def строк(p):
    if not os.path.exists(p):
        return 0
    n = 0
    with open(p, encoding='utf-8-sig', errors='replace') as f:
        for s in f:
            if s.strip():
                n += 1
    return n


def свежих(папка, минут):
    порог = time.time() - минут * 60
    n = 0
    try:
        with os.scandir(папка) as it:
            for e in it:
                try:
                    if e.is_file() and e.stat().st_mtime >= порог:
                        n += 1
                except OSError:
                    pass
    except OSError:
        return -1
    return n


def цп():
    try:
        out = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage "
             "-Average).Average; (Get-CimInstance Win32_OperatingSystem | "
             "%{[int]($_.FreePhysicalMemory/1024)}); (Get-Process | "
             "Where-Object {$_.ProcessName -like '*Zenno*' -or $_.ProcessName -like 'zbe*'} "
             "| Measure-Object).Count"],
            capture_output=True, text=True, timeout=90)
        return [x.strip() for x in out.stdout.split() if x.strip()]
    except Exception as e:  # noqa: BLE001
        return [str(e)[:80]]


ц = цп()
print(json.dumps({
    'очередь_строк': строк(os.path.join(ZENNO, 'ochered.txt')),
    'отдано_строк': строк(os.path.join(ZENNO, 'otdano.txt')),
    'gotovo_файлов': свежих(os.path.join(ZENNO, 'gotovo'), 10 ** 6),
    'gotovo_за_30мин': свежих(os.path.join(ZENNO, 'gotovo'), 30),
    'pagecache_всего': свежих(KESH, 10 ** 7),
    'pagecache_за_30мин': свежих(KESH, 30),
    'цп_проц__свободно_мб__процессов_зенки': ц,
}, ensure_ascii=False, indent=1))
