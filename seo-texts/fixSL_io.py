# -*- coding: utf-8 -*-
r"""fixSL (21.10): кто сильнее всех читает/пишет диск сервера (топ процессов по I/O). Только чтение.

    python3 zapusk_na_servere.py fixSL_io.py
"""
import re
import subprocess

w = subprocess.run('wmic path Win32_PerfFormattedData_PerfProc_Process get Name,IDProcess,IOReadBytesPersec,IOWriteBytesPersec,'
                   'WorkingSetPrivate /format:csv', shell=True, capture_output=True, text=True, errors='replace').stdout
rows = []
for l in w.splitlines():
    p = l.split(',')
    if len(p) >= 6 and p[2].isdigit() and p[3] not in ('_Total', 'Idle'):
        rows.append((int(p[2]) + int(p[3]), p[4], p[1], int(p[2]), int(p[3]), int(p[5]) if p[5].isdigit() else 0))
print('топ по диску (имя, pid, чтение МБ/с, запись МБ/с, память МБ):')
for s, imya, pid, r, wr, mem in sorted(rows, reverse=True)[:10]:
    cl = subprocess.run('wmic process where processid=%s get CommandLine /format:list' % pid, shell=True, capture_output=True,
                        text=True, errors='replace').stdout.strip().replace('CommandLine=', '')
    cl = re.sub(r'(?i)(token|key|secret|password)\S*', '<скрыто>', cl)
    print('  %-22s %6s %7.1f %7.1f %6d  %s' % (imya, pid, r / 2**20, wr / 2**20, mem // 2**20, cl[:110]))
