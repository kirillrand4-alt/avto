# -*- coding: utf-8 -*-
# Остановить ВСЕ экземпляры ca_fns_reestr.py (09.11: раннер перезапускал запуск по таймауту — 4 копии писали в один
# .part), удалить битую докачку rsmp. Чужие процессы не трогаем: фильтр по имени нашего скрипта в командной строке.
import glob, json, os, subprocess
мой = os.getpid()
out = subprocess.run(['powershell', '-NoProfile', '-Command',
                      "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*ca_fns_reestr.py*' } | "
                      "Select-Object ProcessId,CommandLine | ConvertTo-Json"], capture_output=True, text=True).stdout
пп = json.loads(out) if out.strip() else []
пп = [пп] if isinstance(пп, dict) else пп
убито = []
for p in пп:
    if p['ProcessId'] != мой:
        subprocess.run(['taskkill', '/PID', str(p['ProcessId']), '/F'], capture_output=True)
        убито.append(p['ProcessId'])
уд = []
for f in glob.glob(r'C:\sender\_ops\ak\fns\data-*-structure-*.zip.part') + [r'C:\sender\server\ca\ca_fns_reestr.lock']:
    if os.path.exists(f):
        os.remove(f)
        уд.append(os.path.basename(f))
print('===ИТОГ===', json.dumps({'убито': убито, 'удалено': уд}, ensure_ascii=False))
