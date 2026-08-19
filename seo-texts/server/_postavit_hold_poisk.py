# -*- coding: utf-8 -*-
"""Положить HOLD-POISK.flag и погасить поиск сайтов, если он крутится."""
import io
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
io.open(r'C:\sender\server\HOLD-POISK.flag', 'w', encoding='utf-8').write(
    'холд владельца 19.08: XMLRiver не тратим, качаем страницы по известным сайтам.\n'
    'Снять: удалить файл — сторож поднимет poisk_saytov сам.\n')
убито = []
p = subprocess.run(['wmic', 'process', 'where',
                    "commandline like '%poisk_saytov%' and name like 'python%'",
                    'get', 'processid'], capture_output=True, text=True)
for x in (p.stdout or '').splitlines():
    if x.strip().isdigit():
        subprocess.run(['taskkill', '/PID', x.strip(), '/F'], capture_output=True)
        убито.append(x.strip())
print(json.dumps({'флаг': 'положен', 'убито_поисков': убито}, ensure_ascii=False))
