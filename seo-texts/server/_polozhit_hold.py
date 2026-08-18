# -*- coding: utf-8 -*-
"""Положить HOLD-FAKTY.flag, убить fakty_cikl, прогнать сторожа и показать итог."""
import io
import json
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
io.open(r'C:\sender\server\HOLD-FAKTY.flag', 'w', encoding='utf-8').write(
    'холд владельца 17.08: обогащение карточек через провайдера остановлено.\n'
    'Снять: удалить этот файл — сторож поднимет fakty_cikl сам в течение 10 минут.\n')
p = subprocess.run(['wmic', 'process', 'where',
                    "commandline like '%fakty_cikl%' and name like 'python%'",
                    'get', 'processid'], capture_output=True, text=True)
итог['убито_fakty_cikl'] = []
for x in (p.stdout or '').splitlines():
    if x.strip().isdigit():
        r = subprocess.run(['taskkill', '/PID', x.strip(), '/F'],
                           capture_output=True, text=True)
        итог['убито_fakty_cikl'].append({'pid': x.strip(), 'rc': r.returncode})
time.sleep(2)
s = subprocess.run([sys.executable, r'C:\sender\server\storozh.py'],
                   capture_output=True, text=True, cwd=r'C:\sender\server',
                   timeout=240)
итог['сторож_прогон'] = (s.stdout or s.stderr or '')[-500:]
p2 = subprocess.run(['wmic', 'process', 'where',
                     "commandline like '%fakty_cikl%' and name like 'python%'",
                     'get', 'processid'], capture_output=True, text=True)
итог['fakty_cikl_после'] = [x.strip() for x in (p2.stdout or '').splitlines()
                            if x.strip().isdigit()]
print(json.dumps(итог, ensure_ascii=False, indent=1))
