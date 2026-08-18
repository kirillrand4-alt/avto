# -*- coding: utf-8 -*-
"""Остановить обогащение карточек через провайдера (команда владельца 17.08).

Глушим fakty_cikl.py (цикл паспортов) и enrich_contacts.py (обход с
извлечением). Раннер (job_runner), панель, дроп, unsub и NewsScan не трогаем.
Резюм встроен в сами конвейеры: site_facts пропускает готовых по format/ts,
enrich_contacts держит очередь и результаты в enrich.db — перезапуск одной
командой добьёт остаток с места остановки.
"""
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
убито = []
for метка in ('fakty_cikl', 'enrich_contacts.py'):
    p = subprocess.run(['wmic', 'process', 'where',
                        "commandline like '%%%s%%' and name like 'python%%'" % метка,
                        'get', 'processid'], capture_output=True, text=True)
    for x in (p.stdout or '').splitlines():
        pid = x.strip()
        if pid.isdigit():
            subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True)
            убито.append({'что': метка, 'pid': pid})
print(json.dumps({'убито': убито}, ensure_ascii=False, indent=1))
